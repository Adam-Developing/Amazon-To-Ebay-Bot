from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, render_template, request

from amazon import scrape_amazon
from bulk_parser import parse_bulk_items
from ebay import list_on_ebay
from tokens import (
    clear_user_token,
    get_application_token,
    get_ebay_user_token,
    load_tokens,
    save_tokens,
    set_oauth_callback_code,
)
from ui_bridge import IOBridge

app = Flask(__name__)

MAX_LOG_ENTRIES = 1000
PROMPT_TIMEOUT_SECONDS = 600
MAX_UPLOAD_BYTES = 2 * 1024 * 1024

FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
EPHEMERAL_SECRET = False
if not FLASK_SECRET_KEY:
    FLASK_SECRET_KEY = os.urandom(24)
    EPHEMERAL_SECRET = True

app.secret_key = FLASK_SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

STATE_LOCK = threading.Lock()
LOG_LOCK = threading.Lock()
PROMPT_LOCK = threading.Lock()
OPEN_URL_LOCK = threading.Lock()

STATE: Dict[str, Any] = {
    "product": None,
    "processing": False,
    "status": {
        "label": "Idle",
        "message": "Ready to start.",
        "tone": "idle",
    },
    "bulk": {
        "running": False,
        "paused": False,
        "cancelled": False,
        "processed": 0,
        "total": 0,
        "items": [],
    },
}

LOG_ENTRIES: List[Dict[str, Any]] = []
LOG_COUNTER = 0

PROMPT_EVENTS: Dict[int, Dict[str, Any]] = {}
ACTIVE_PROMPT: Optional[Dict[str, Any]] = None
PROMPT_COUNTER = 0

OPEN_URLS: List[str] = []

bulk_pause_event = threading.Event()
bulk_cancel_event = threading.Event()


def _set_processing(value: bool) -> None:
    with STATE_LOCK:
        STATE["processing"] = value


def _set_status(label: str, message: str, tone: str = "idle") -> None:
    with STATE_LOCK:
        STATE["status"] = {"label": label, "message": message, "tone": tone}


def _set_product(product: Optional[Dict[str, Any]]) -> None:
    with STATE_LOCK:
        STATE["product"] = product


def _is_processing() -> bool:
    with STATE_LOCK:
        return bool(STATE["processing"])


def _is_bulk_running() -> bool:
    with STATE_LOCK:
        return bool(STATE["bulk"]["running"])


def _update_bulk_state(**updates: Any) -> None:
    with STATE_LOCK:
        STATE["bulk"].update(updates)


def _build_bulk_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    prepared = []
    for idx, item in enumerate(items, start=1):
        prepared.append(
            {
                "index": idx,
                "url": item.get("url", ""),
                "quantity": item.get("quantity", 1),
                "note": item.get("note", ""),
                "custom_specifics": item.get("custom_specifics", {}),
                "title": item.get("title", ""),
                "status": "Ready",
                "message": "",
            }
        )
    return prepared


def _set_bulk_items(items: List[Dict[str, Any]]) -> None:
    _update_bulk_state(items=items, total=len(items), processed=0)


def _update_bulk_item(index: int, status: str, message: str = "") -> None:
    updated = False
    items_copy = None
    with STATE_LOCK:
        items = STATE["bulk"].get("items", [])
        if 0 <= index < len(items):
            items[index]["status"] = status
            items[index]["message"] = message
            updated = True
            # make a shallow copy of items for the updater to publish outside the lock
            items_copy = [dict(it) for it in items]
    if updated:
        # Publish the updated items into STATE via the helper so api_state will return them
        _update_bulk_state(items=items_copy)
        _append_log(f"Bulk item {index + 1} status updated to '{status}': {message}")
    else:
        _append_log(f"Bulk item index {index} is out of range.")


def _append_log(msg: str) -> None:
    global LOG_COUNTER
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    with LOG_LOCK:
        LOG_COUNTER += 1
        LOG_ENTRIES.append({"id": LOG_COUNTER, "message": entry})
        if len(LOG_ENTRIES) > MAX_LOG_ENTRIES:
            LOG_ENTRIES[: len(LOG_ENTRIES) - MAX_LOG_ENTRIES] = []


def _queue_open_url(url: str) -> None:
    with OPEN_URL_LOCK:
        OPEN_URLS.append(url)


class WebIOBridge(IOBridge):
    def log(self, msg: str) -> None:
        _append_log(str(msg))

    def prompt_text(self, prompt: str, default: str = "") -> str:
        return _await_prompt("text", prompt, default, [])

    def prompt_choice(self, prompt: str, options: List[str]) -> Optional[str]:
        value = _await_prompt("choice", prompt, "", options)
        if value is not None:
            return value
        return options[0] if options else None

    def open_url(self, url: str) -> None:
        _queue_open_url(url)
        _append_log(f"Opening URL: {url}")


WEB_IO = WebIOBridge()


def _await_prompt(prompt_type: str, prompt: str, default: str, options: List[str]) -> str:
    global PROMPT_COUNTER, ACTIVE_PROMPT
    event = threading.Event()
    with PROMPT_LOCK:
        PROMPT_COUNTER += 1
        rid = PROMPT_COUNTER
        ACTIVE_PROMPT = {
            "id": rid,
            "type": prompt_type,
            "prompt": prompt,
            "default": default,
            "options": options,
        }
        PROMPT_EVENTS[rid] = {"event": event, "value": None, "default": default}
    resolved = event.wait(PROMPT_TIMEOUT_SECONDS)
    with PROMPT_LOCK:
        entry = PROMPT_EVENTS.pop(rid, None)
        ACTIVE_PROMPT = None
    if not resolved:
        _append_log("Prompt timed out; continuing with default value.")
        return default
    if not entry:
        return default
    value = entry.get("value")
    return value if value is not None else default


def _resolve_prompt(rid: int, value: Optional[str]) -> bool:
    global ACTIVE_PROMPT
    with PROMPT_LOCK:
        entry = PROMPT_EVENTS.get(rid)
        if not entry:
            return False
        entry["value"] = value
        entry["event"].set()
        ACTIVE_PROMPT = None
    return True


def _ensure_ebay_auth() -> Optional[Dict[str, Any]]:
    try:
        tokens = load_tokens() or {}
        app_token = get_application_token(tokens, WEB_IO)
        if not app_token:
            WEB_IO.log("Failed to ensure application token.")
            return None
        tokens["application_token"] = app_token
        save_tokens(tokens, WEB_IO)
        user_token = get_ebay_user_token(tokens, WEB_IO)
        if not user_token:
            WEB_IO.log("Failed to ensure user token.")
            return None
        tokens["user_token"] = user_token
        save_tokens(tokens, WEB_IO)
        return tokens
    except Exception as exc:
        WEB_IO.log(f"Auth ensure error: {exc}")
        return None


def _parse_custom_specifics(raw: str) -> Dict[str, str]:
    custom_specifics: Dict[str, str] = {}
    for part in raw.split("|"):
        if ":" in part:
            key, value = part.split(":", 1)
            if key.strip() and value.strip():
                custom_specifics[key.strip()] = value.strip()
    return custom_specifics


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/callback")
def oauth_callback():
    code = request.args.get("code")
    if code:
        set_oauth_callback_code(code)
        return "<h1>Authentication Successful!</h1><p>You can now return to the app.</p>"
    return "Authentication failed.", 400


@app.get("/api/state")
def api_state():
    with STATE_LOCK:
        bulk_state = dict(STATE["bulk"])
        bulk_state["items"] = [dict(item) for item in bulk_state.get("items", [])]
        state = {
            "product_loaded": STATE["product"] is not None,
            "processing": STATE["processing"],
            "status": dict(STATE["status"]),
            "bulk": bulk_state,
        }
    return jsonify(state)


@app.get("/api/logs")
def api_logs():
    since = int(request.args.get("since", 0))
    with LOG_LOCK:
        entries = [entry for entry in LOG_ENTRIES if entry["id"] > since]
        last_id = LOG_ENTRIES[-1]["id"] if LOG_ENTRIES else since
    return jsonify({"entries": entries, "last_id": last_id})


@app.post("/api/log")
def api_log():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if message:
        _append_log(message)
    return jsonify({"ok": True})


@app.get("/api/prompts")
def api_prompts():
    with PROMPT_LOCK:
        prompt = dict(ACTIVE_PROMPT) if ACTIVE_PROMPT else None
    return jsonify({"prompt": prompt})


@app.post("/api/prompts/<int:rid>")
def api_prompt_response(rid: int):
    payload = request.get_json(silent=True) or {}
    value = payload.get("value")
    resolved = _resolve_prompt(rid, value)
    return jsonify({"ok": resolved})


@app.get("/api/open-urls")
def api_open_urls():
    with OPEN_URL_LOCK:
        urls = list(OPEN_URLS)
        OPEN_URLS.clear()
    return jsonify({"urls": urls})


@app.post("/api/load-json")
def api_load_json():
    file = request.files.get("file")
    if not file:
        return jsonify({"ok": False, "error": "No file uploaded."}), 400
    try:
        raw = file.read(MAX_UPLOAD_BYTES + 1)
        if len(raw) > MAX_UPLOAD_BYTES:
            return jsonify({"ok": False, "error": "Uploaded JSON file is too large."}), 413
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
        return jsonify({"ok": False, "error": f"Failed to parse JSON: {exc}"}), 400
    _set_product(data)
    _append_log(f"Loaded product from {file.filename}")
    _set_status("Ready", "Product loaded from JSON.", "success")
    response = {
        "ok": True,
        "url": data.get("URL", ""),
        "quantity": data.get("quantity", ""),
        "seller_note": data.get("sellerNote", ""),
    }
    return jsonify(response)


@app.post("/api/auth")
def api_auth():
    if _is_processing():
        return jsonify({"ok": False, "error": "Another task is running."}), 400
    _set_status("Working", "Authorizing eBay...", "working")

    def work():
        _set_processing(True)
        try:
            tokens = load_tokens()
            app_token = get_application_token(tokens, WEB_IO)
            if not app_token:
                _set_status("Attention", "Failed to get application token.", "error")
                return
            tokens["application_token"] = app_token
            save_tokens(tokens, WEB_IO)
            user_token = get_ebay_user_token(tokens, WEB_IO)
            if not user_token:
                _set_status("Attention", "Failed to get user token.", "error")
                return
            tokens["user_token"] = user_token
            save_tokens(tokens, WEB_IO)
            WEB_IO.log("All tokens are ready.")
            _set_status("Ready", "All tokens are ready.", "success")
        finally:
            _set_processing(False)

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


@app.post("/api/logout")
def api_logout():
    if _is_processing():
        return jsonify({"ok": False, "error": "Another task is running."}), 400
    _set_status("Working", "Logging out of eBay...", "working")

    def work():
        _set_processing(True)
        try:
            ok = clear_user_token(WEB_IO)
            if ok:
                WEB_IO.log("User token cleared. Re-authorize to reconnect your eBay account.")
                _set_status("Ready", "Logged out from eBay.", "success")
            else:
                WEB_IO.log("Failed to clear user token. Check permissions and try again.")
                _set_status("Attention", "Failed to clear the eBay user token.", "error")
        finally:
            _set_processing(False)

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


@app.post("/api/scrape")
def api_scrape():
    if _is_processing():
        return jsonify({"ok": False, "error": "Another task is running."}), 400
    payload = request.get_json(silent=True) or {}
    url = str(payload.get("url", "")).strip()
    if not url:
        return jsonify({"ok": False, "error": "Please enter an Amazon URL."}), 400
    note = str(payload.get("note", "")).strip()
    quantity = payload.get("quantity")
    qty_value: Optional[int] = None
    if quantity not in (None, ""):
        try:
            qty_value = int(quantity)
        except (ValueError, TypeError):
            qty_value = None
    custom_specs_raw = str(payload.get("custom_specs", "")).strip()
    custom_specs = _parse_custom_specifics(custom_specs_raw) if custom_specs_raw else {}
    _set_status("Working", "Scraping Amazon product...", "working")

    def work():
        _set_processing(True)
        try:
            product = scrape_amazon(url, note=note, quantity=qty_value, custom_specifics=custom_specs, io=WEB_IO)
            _set_product(product)
            WEB_IO.log("Product scraped. You can now list on eBay.")
            _set_status("Ready", "Product scraped. Ready to list.", "success")
            try:
                with open("product.json", "w", encoding="utf-8") as handle:
                    json.dump(product, handle, indent=2)
            except (OSError, TypeError, ValueError) as exc:
                WEB_IO.log(f"Failed to write product.json: {exc}")
        finally:
            _set_processing(False)

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


@app.post("/api/list")
def api_list():
    if _is_processing():
        return jsonify({"ok": False, "error": "Another task is running."}), 400
    with STATE_LOCK:
        product = STATE["product"]
    if not product:
        return jsonify({"ok": False, "error": "Please scrape or load a product first."}), 400
    _set_status("Working", "Listing item on eBay...", "working")

    def work():
        _set_processing(True)
        try:
            ensured = _ensure_ebay_auth()
            if not ensured:
                WEB_IO.log("Authentication failed. Check credentials and try again.")
                _set_status("Attention", "Authentication failed. Check credentials.", "error")
                return
            result = list_on_ebay(product, WEB_IO)
            if result.get("ok"):
                WEB_IO.log(f"Listing complete. Item ID: {result.get('item_id')}")
                _set_status("Ready", f"Listing complete. Item ID {result.get('item_id')}.", "success")
            else:
                WEB_IO.log(f"Listing failed: {result}")
                _set_status("Attention", "Listing failed. See log for details.", "error")
        finally:
            _set_processing(False)

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


@app.post("/api/bulk/preview")
def api_bulk_preview():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    with STATE_LOCK:
        if STATE["bulk"]["running"]:
            items = [dict(item) for item in STATE["bulk"].get("items", [])]
            return jsonify({"ok": True, "items": items})
    if not text:
        _set_bulk_items([])
        return jsonify({"ok": True, "items": []})
    items = parse_bulk_items(text)
    prepared = _build_bulk_items(items)
    _set_bulk_items(prepared)
    return jsonify({"ok": True, "items": prepared})


@app.post("/api/bulk/process")
def api_bulk_process():
    if _is_bulk_running():
        return jsonify({"ok": False, "error": "Bulk processing is already running."}), 400
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    if not text:
        return jsonify({"ok": False, "error": "Paste bulk text first."}), 400
    items = parse_bulk_items(text)
    if not items:
        return jsonify({"ok": False, "error": "No items could be parsed from the text."}), 400
    prepared_items = _build_bulk_items(items)
    _set_bulk_items(prepared_items)
    _set_status("Working", f"Bulk processing started ({len(items)} items).", "working")

    def work():
        _update_bulk_state(running=True, paused=False, cancelled=False, processed=0, total=len(prepared_items))
        bulk_pause_event.set()
        bulk_cancel_event.clear()
        try:
            ensured = _ensure_ebay_auth()
            if not ensured:
                WEB_IO.log("Authentication failed. Check credentials and try again.")
                _set_status("Attention", "Authentication failed. Check credentials.", "error")
                return
            os.makedirs("bulk_products", exist_ok=True)
            processed_count = 0
            total_items = len(prepared_items)
            for index, item in enumerate(prepared_items):
                display_index = item.get("index", index + 1)
                bulk_pause_event.wait()
                if bulk_cancel_event.is_set():
                    WEB_IO.log("Bulk process cancelled.")
                    _update_bulk_item(index, "Cancelled", "Cancelled before processing.")
                    for remaining_index in range(index + 1, total_items):
                        _update_bulk_item(remaining_index, "Cancelled", "Cancelled before processing.")
                    break
                _set_status("Working", f"Processing item {display_index} of {total_items}.", "working")
                _update_bulk_item(index, "Scraping", "Scraping Amazon listing.")
                WEB_IO.log(f"=== Processing Item {display_index}/{total_items} ===")
                product = scrape_amazon(
                    item.get("url", ""),
                    note=item.get("note", ""),
                    quantity=item.get("quantity", 1),
                    custom_specifics=item.get("custom_specifics", {}),
                    io=WEB_IO,
                )
                if not product:
                    WEB_IO.log(f"Skipping item {display_index} due to scraping failure.")
                    _update_bulk_item(index, "Failed", "Scrape failed.")
                    continue
                with open(
                    os.path.join("bulk_products", f"product_{display_index}.json"),
                    "w",
                    encoding="utf-8",
                ) as handle:
                    json.dump(product, handle, indent=2)
                _update_bulk_item(index, "Listing", "Listing on eBay.")
                result = list_on_ebay(product, WEB_IO)
                if result.get("ok"):
                    processed_count += 1
                    _update_bulk_item(
                        index,
                        "Listed",
                        f"Listed successfully (Item ID {result.get('item_id')}).",
                    )
                else:
                    _update_bulk_item(index, "Failed", "Listing failed.")
                _update_bulk_state(processed=processed_count)
            if not bulk_cancel_event.is_set():
                WEB_IO.log(f"Bulk processing finished. Processed {processed_count} items.")
                _set_status("Ready", "Bulk processing finished.", "success")
            else:
                _set_status("Attention", "Bulk processing cancelled.", "warning")
        finally:
            _update_bulk_state(running=False, paused=False, cancelled=bulk_cancel_event.is_set())

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


@app.post("/api/bulk/pause")
def api_bulk_pause():
    if not _is_bulk_running():
        return jsonify({"ok": False, "error": "Bulk processing is not running."}), 400
    if bulk_pause_event.is_set():
        bulk_pause_event.clear()
        _update_bulk_state(paused=True)
        WEB_IO.log("Bulk processing paused.")
        _set_status("Paused", "Bulk processing paused.", "warning")
        return jsonify({"ok": True, "paused": True})
    bulk_pause_event.set()
    _update_bulk_state(paused=False)
    WEB_IO.log("Bulk processing resumed.")
    _set_status("Working", "Bulk processing resumed.", "working")
    return jsonify({"ok": True, "paused": False})


@app.post("/api/bulk/cancel")
def api_bulk_cancel():
    if not _is_bulk_running():
        return jsonify({"ok": False, "error": "Bulk processing is not running."}), 400
    bulk_cancel_event.set()
    if not bulk_pause_event.is_set():
        bulk_pause_event.set()
    _update_bulk_state(cancelled=True)
    WEB_IO.log("Cancellation requested...")
    _set_status("Attention", "Bulk processing cancellation requested.", "warning")
    return jsonify({"ok": True})


def run_web(host: str = "127.0.0.1", port: int = 5000) -> None:
    if host not in {"127.0.0.1", "localhost"}:
        _append_log(
            "Warning: binding to a non-local host exposes the web UI to external connections without "
            "authentication. Use only on trusted networks."
        )
    if EPHEMERAL_SECRET:
        _append_log("FLASK_SECRET_KEY not set; sessions will reset on each restart.")
    _append_log("Starting web UI...")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_web()
