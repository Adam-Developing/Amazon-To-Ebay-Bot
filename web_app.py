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

DEFAULT_NEW_TAB_URL = os.getenv("DEFAULT_NEW_TAB_URL", "https://www.google.com")

STATE_LOCK = threading.Lock()
LOG_LOCK = threading.Lock()
PROMPT_LOCK = threading.Lock()
OPEN_URL_LOCK = threading.Lock()

STATE: Dict[str, Any] = {
    "product": None,
    "processing": False,
    "bulk": {
        "running": False,
        "paused": False,
        "cancelled": False,
        "processed": 0,
        "total": 0,
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


def _append_log(msg: str) -> None:
    global LOG_COUNTER
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    with LOG_LOCK:
        LOG_COUNTER += 1
        LOG_ENTRIES.append({"id": LOG_COUNTER, "message": entry})


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
    event.wait()
    with PROMPT_LOCK:
        entry = PROMPT_EVENTS.pop(rid, None)
        ACTIVE_PROMPT = None
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
    return render_template("index.html", default_new_tab_url=DEFAULT_NEW_TAB_URL)


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
        state = {
            "product_loaded": STATE["product"] is not None,
            "processing": STATE["processing"],
            "bulk": STATE["bulk"],
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
        data = json.loads(file.read().decode("utf-8"))
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Failed to parse JSON: {exc}"}), 400
    _set_product(data)
    _append_log(f"Loaded product from {file.filename}")
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

    def work():
        _set_processing(True)
        try:
            tokens = load_tokens()
            app_token = get_application_token(tokens, WEB_IO)
            if not app_token:
                return
            tokens["application_token"] = app_token
            save_tokens(tokens, WEB_IO)
            user_token = get_ebay_user_token(tokens, WEB_IO)
            if not user_token:
                return
            tokens["user_token"] = user_token
            save_tokens(tokens, WEB_IO)
            WEB_IO.log("All tokens are ready.")
        finally:
            _set_processing(False)

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


@app.post("/api/logout")
def api_logout():
    if _is_processing():
        return jsonify({"ok": False, "error": "Another task is running."}), 400

    def work():
        _set_processing(True)
        try:
            ok = clear_user_token(WEB_IO)
            if ok:
                WEB_IO.log("User token cleared. Re-authorize to reconnect your eBay account.")
            else:
                WEB_IO.log("Failed to clear user token. Check permissions and try again.")
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
        except Exception:
            qty_value = None
    custom_specs_raw = str(payload.get("custom_specs", "")).strip()
    custom_specs = _parse_custom_specifics(custom_specs_raw) if custom_specs_raw else {}

    def work():
        _set_processing(True)
        try:
            product = scrape_amazon(url, note=note, quantity=qty_value, custom_specifics=custom_specs, io=WEB_IO)
            _set_product(product)
            WEB_IO.log("Product scraped. You can now list on eBay.")
            try:
                with open("product.json", "w", encoding="utf-8") as handle:
                    json.dump(product, handle, indent=2)
            except Exception as exc:
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

    def work():
        _set_processing(True)
        try:
            ensured = _ensure_ebay_auth()
            if not ensured:
                WEB_IO.log("Authentication failed. Check credentials and try again.")
                return
            result = list_on_ebay(product, WEB_IO)
            if result.get("ok"):
                WEB_IO.log(f"Listing complete. Item ID: {result.get('item_id')}")
            else:
                WEB_IO.log(f"Listing failed: {result}")
        finally:
            _set_processing(False)

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


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

    def work():
        _update_bulk_state(running=True, paused=False, cancelled=False, processed=0, total=len(items))
        bulk_pause_event.set()
        bulk_cancel_event.clear()
        try:
            ensured = _ensure_ebay_auth()
            if not ensured:
                WEB_IO.log("Authentication failed. Check credentials and try again.")
                return
            os.makedirs("bulk_products", exist_ok=True)
            processed_count = 0
            total_items = len(items)
            for idx, item in enumerate(items, start=1):
                bulk_pause_event.wait()
                if bulk_cancel_event.is_set():
                    WEB_IO.log("Bulk process cancelled.")
                    break
                WEB_IO.log(f"=== Processing Item {idx}/{total_items} ===")
                product = scrape_amazon(
                    item.get("url", ""),
                    note=item.get("note", ""),
                    quantity=item.get("quantity", 1),
                    custom_specifics=item.get("custom_specifics", {}),
                    io=WEB_IO,
                )
                if not product:
                    WEB_IO.log(f"Skipping item {idx} due to scraping failure.")
                    continue
                with open(os.path.join("bulk_products", f"product_{idx}.json"), "w", encoding="utf-8") as handle:
                    json.dump(product, handle, indent=2)
                result = list_on_ebay(product, WEB_IO)
                if result.get("ok"):
                    processed_count += 1
                _update_bulk_state(processed=processed_count)
            if not bulk_cancel_event.is_set():
                WEB_IO.log(f"Bulk processing finished. Processed {processed_count} items.")
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
        return jsonify({"ok": True, "paused": True})
    bulk_pause_event.set()
    _update_bulk_state(paused=False)
    WEB_IO.log("Bulk processing resumed.")
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
    return jsonify({"ok": True})


def run_web(host: str = "127.0.0.1", port: int = 5000) -> None:
    _append_log("Starting web UI...")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_web()
