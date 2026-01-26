from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import (
    Flask,
    g,
    has_app_context,
    has_request_context,
    jsonify,
    render_template,
    request,
    session,
)

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
UPDATE_WAIT_SECONDS = 25

FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
EPHEMERAL_SECRET = False
if not FLASK_SECRET_KEY:
    FLASK_SECRET_KEY = os.urandom(24)
    EPHEMERAL_SECRET = True

app.secret_key = FLASK_SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

USER_CONTEXTS: Dict[str, Dict[str, Any]] = {}
USER_CONTEXTS_LOCK = threading.Lock()


def _new_state() -> Dict[str, Any]:
    return {
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


def _create_user_context() -> Dict[str, Any]:
    update_lock = threading.Lock()
    return {
        "state": _new_state(),
        "state_lock": threading.Lock(),
        "log_entries": [],
        "log_counter": 0,
        "log_lock": threading.Lock(),
        "prompt_events": {},
        "active_prompt": None,
        "prompt_counter": 0,
        "prompt_lock": threading.Lock(),
        "open_urls": [],
        "open_url_lock": threading.Lock(),
        "bulk_pause_event": threading.Event(),
        "bulk_cancel_event": threading.Event(),
        "update_counter": 0,
        "update_lock": update_lock,
        "update_condition": threading.Condition(update_lock),
    }


def _get_user_id() -> str:
    user_id = session.get("user_id")
    if not user_id:
        user_id = secrets.token_urlsafe(16)
        session["user_id"] = user_id
    return user_id


def _current_user_id() -> str:
    if has_request_context() or has_app_context():
        return getattr(g, "user_id", "system")
    return "system"


def _get_user_context(user_id: str) -> Dict[str, Any]:
    with USER_CONTEXTS_LOCK:
        context = USER_CONTEXTS.get(user_id)
        if not context:
            context = _create_user_context()
            USER_CONTEXTS[user_id] = context
        return context


@app.before_request
def _load_user() -> None:
    g.user_id = _get_user_id()


def _notify_update() -> None:
    context = _get_user_context(g.user_id)
    condition = context["update_condition"]
    with condition:
        context["update_counter"] += 1
        condition.notify_all()


def _set_processing(value: bool) -> None:
    context = _get_user_context(g.user_id)
    with context["state_lock"]:
        context["state"]["processing"] = value
    _notify_update()


def _set_status(label: str, message: str, tone: str = "idle") -> None:
    context = _get_user_context(g.user_id)
    with context["state_lock"]:
        context["state"]["status"] = {"label": label, "message": message, "tone": tone}
    _notify_update()


def _set_product(product: Optional[Dict[str, Any]]) -> None:
    context = _get_user_context(g.user_id)
    with context["state_lock"]:
        context["state"]["product"] = product
    _notify_update()


def _is_processing() -> bool:
    context = _get_user_context(g.user_id)
    with context["state_lock"]:
        return bool(context["state"]["processing"])


def _is_bulk_running() -> bool:
    context = _get_user_context(g.user_id)
    with context["state_lock"]:
        return bool(context["state"]["bulk"]["running"])


def _update_bulk_state(**updates: Any) -> None:
    context = _get_user_context(g.user_id)
    with context["state_lock"]:
        context["state"]["bulk"].update(updates)
    _notify_update()


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
    context = _get_user_context(g.user_id)
    updated = False
    items_copy = None
    with context["state_lock"]:
        items = context["state"]["bulk"].get("items", [])
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
    context = _get_user_context(g.user_id)
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    with context["log_lock"]:
        context["log_counter"] += 1
        context["log_entries"].append({"id": context["log_counter"], "message": entry})
        if len(context["log_entries"]) > MAX_LOG_ENTRIES:
            context["log_entries"][: len(context["log_entries"]) - MAX_LOG_ENTRIES] = []
    _notify_update()


def _queue_open_url(url: str) -> None:
    context = _get_user_context(g.user_id)
    with context["open_url_lock"]:
        context["open_urls"].append(url)
    _notify_update()


class WebIOBridge(IOBridge):
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id

    def log(self, msg: str) -> None:
        _append_log(str(msg))

    def prompt_text(self, prompt: str, default: str = "", options: List[str] | None = None) -> str:
        # Allow passing suggestions for FREE_TEXT prompts (shown as typeable dropdown in UI)
        return _await_prompt("text", prompt, default, options or [])

    def prompt_choice(self, prompt: str, options: List[str]) -> Optional[str]:
        value = _await_prompt("choice", prompt, "", options)
        if value is not None:
            return value
        return options[0] if options else None

    def open_url(self, url: str) -> None:
        _queue_open_url(url)
        _append_log(f"Opening URL: {url}")


def _get_web_io() -> WebIOBridge:
    return WebIOBridge(g.user_id)


def _await_prompt(prompt_type: str, prompt: str, default: str, options: List[str]) -> str:
    context = _get_user_context(g.user_id)
    event = threading.Event()
    with context["prompt_lock"]:
        context["prompt_counter"] += 1
        rid = context["prompt_counter"]
        context["active_prompt"] = {
            "id": rid,
            "type": prompt_type,
            "prompt": prompt,
            "default": default,
            "options": options,
        }
        context["prompt_events"][rid] = {"event": event, "value": None, "default": default}
    _notify_update()
    resolved = event.wait(PROMPT_TIMEOUT_SECONDS)
    with context["prompt_lock"]:
        entry = context["prompt_events"].pop(rid, None)
        context["active_prompt"] = None
    _notify_update()
    if not resolved:
        _append_log("Prompt timed out; continuing with default value.")
        return default
    if not entry:
        return default
    value = entry.get("value")
    return value if value is not None else default


def _resolve_prompt(rid: int, value: Optional[str]) -> bool:
    context = _get_user_context(g.user_id)
    with context["prompt_lock"]:
        entry = context["prompt_events"].get(rid)
        if not entry:
            return False
        entry["value"] = value
        entry["event"].set()
        context["active_prompt"] = None
    _notify_update()
    return True


def _ensure_ebay_auth() -> Optional[Dict[str, Any]]:
    web_io = _get_web_io()
    user_id = g.user_id
    try:
        tokens = load_tokens(user_id) or {}
        app_token = get_application_token(tokens, web_io)
        if not app_token:
            web_io.log("Failed to ensure application token.")
    return None
        tokens["application_token"] = app_token
        save_tokens(tokens, web_io, user_id)
        user_token = get_ebay_user_token(tokens, web_io, state=user_id)
        if not user_token:
            web_io.log("Failed to ensure user token.")
            return None
        tokens["user_token"] = user_token
        save_tokens(tokens, web_io, user_id)
        return tokens
    except Exception as exc:
        web_io.log(f"Auth ensure error: {exc}")
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
    _get_user_context(g.user_id)
    return render_template("index.html", initial_tab="single")


@app.route("/bulk")
def bulk() -> str:
    _get_user_context(g.user_id)
    return render_template("index.html", initial_tab="bulk")


@app.route("/callback")
def oauth_callback():
    code = request.args.get("code")
    state = request.args.get("state")
    if code:
        set_oauth_callback_code(code, state=state)
        return "<h1>Authentication Successful!</h1><p>You can now return to the app.</p>"
    return "Authentication failed.", 400


@app.get("/api/state")
def api_state():
    context = _get_user_context(g.user_id)
    with context["state_lock"]:
        bulk_state = dict(context["state"]["bulk"])
        bulk_state["items"] = [dict(item) for item in bulk_state.get("items", [])]
        state = {
            "product_loaded": context["state"]["product"] is not None,
            "processing": context["state"]["processing"],
            "status": dict(context["state"]["status"]),
            "bulk": bulk_state,
        }
    return jsonify(state)


@app.get("/api/logs")
def api_logs():
    since = int(request.args.get("since", 0))
    context = _get_user_context(g.user_id)
    with context["log_lock"]:
        entries = [entry for entry in context["log_entries"] if entry["id"] > since]
        last_id = context["log_entries"][-1]["id"] if context["log_entries"] else since
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
    context = _get_user_context(g.user_id)
    with context["prompt_lock"]:
        prompt = dict(context["active_prompt"]) if context["active_prompt"] else None
    return jsonify({"prompt": prompt})


@app.post("/api/prompts/<int:rid>")
def api_prompt_response(rid: int):
    payload = request.get_json(silent=True) or {}
    value = payload.get("value")
    resolved = _resolve_prompt(rid, value)
    return jsonify({"ok": resolved})


@app.get("/api/open-urls")
def api_open_urls():
    context = _get_user_context(g.user_id)
    with context["open_url_lock"]:
        urls = list(context["open_urls"])
        context["open_urls"].clear()
    return jsonify({"urls": urls})


@app.get("/api/updates")
def api_updates():
    since = request.args.get("since")
    try:
        since_value = int(since) if since is not None else 0
    except ValueError:
        since_value = 0
    if since_value < 0:
        return jsonify({"error": "Invalid since value."}), 400
    context = _get_user_context(g.user_id)
    condition = context["update_condition"]
    with condition:
        if since_value > context["update_counter"]:
            return jsonify({"update_id": context["update_counter"]})
        if context["update_counter"] <= since_value:
            condition.wait(timeout=UPDATE_WAIT_SECONDS)
        current = context["update_counter"]
    return jsonify({"update_id": current})


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
    user_id = g.user_id

    def work():
        with app.app_context():
            g.user_id = user_id
        _set_processing(True)
        try:
            web_io = _get_web_io()
            tokens = load_tokens(user_id)
            app_token = get_application_token(tokens, web_io)
            if not app_token:
                _set_status("Attention", "Failed to get application token.", "error")
                return
            tokens["application_token"] = app_token
            save_tokens(tokens, web_io, user_id)
            user_token = get_ebay_user_token(tokens, web_io, state=user_id)
            if not user_token:
                _set_status("Attention", "Failed to get user token.", "error")
                return
            tokens["user_token"] = user_token
            save_tokens(tokens, web_io, user_id)
            web_io.log("All tokens are ready.")
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
    user_id = g.user_id

    def work():
        with app.app_context():
            g.user_id = user_id
        _set_processing(True)
        try:
            web_io = _get_web_io()
            ok = clear_user_token(web_io, user_id)
            if ok:
                web_io.log("User token cleared. Re-authorize to reconnect your eBay account.")
                _set_status("Ready", "Logged out from eBay.", "success")
            else:
                web_io.log("Failed to clear user token. Check permissions and try again.")
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
    user_id = g.user_id

    def work():
        with app.app_context():
            g.user_id = user_id
        _set_processing(True)
        try:
            web_io = _get_web_io()
            product = scrape_amazon(url, note=note, quantity=qty_value, custom_specifics=custom_specs, io=web_io)
            _set_product(product)
            web_io.log("Product scraped. You can now list on eBay.")
            _set_status("Ready", "Product scraped. Ready to list.", "success")
            try:
                with open("product.json", "w", encoding="utf-8") as handle:
                    json.dump(product, handle, indent=2)
            except (OSError, TypeError, ValueError) as exc:
                _get_web_io().log(f"Failed to write product.json: {exc}")
        finally:
            _set_processing(False)

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


@app.post("/api/list")
def api_list():
    if _is_processing():
        return jsonify({"ok": False, "error": "Another task is running."}), 400
    context = _get_user_context(g.user_id)
    with context["state_lock"]:
        product = context["state"]["product"]
    if not product:
        return jsonify({"ok": False, "error": "Please scrape or load a product first."}), 400
    _set_status("Working", "Listing item on eBay...", "working")
    user_id = g.user_id

    def work():
        with app.app_context():
            g.user_id = user_id
        _set_processing(True)
        try:
            ensured = _ensure_ebay_auth()
            if not ensured:
                _get_web_io().log("Authentication failed. Check credentials and try again.")
                _set_status("Attention", "Authentication failed. Check credentials.", "error")
                return
            result = list_on_ebay(product, _get_web_io())
            if result.get("ok"):
                _get_web_io().log(f"Listing complete. Item ID: {result.get('item_id')}")
                _set_status("Ready", f"Listing complete. Item ID {result.get('item_id')}.", "success")
            else:
                _get_web_io().log(f"Listing failed: {result}")
                _set_status("Attention", "Listing failed. See log for details.", "error")
        finally:
            _set_processing(False)

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


@app.post("/api/bulk/preview")
def api_bulk_preview():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    context = _get_user_context(g.user_id)
    with context["state_lock"]:
        if context["state"]["bulk"]["running"]:
            items = [dict(item) for item in context["state"]["bulk"].get("items", [])]
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
    user_id = g.user_id

    def work():
        with app.app_context():
            g.user_id = user_id
        context = _get_user_context(user_id)
        _update_bulk_state(running=True, paused=False, cancelled=False, processed=0, total=len(prepared_items))
        context["bulk_pause_event"].set()
        context["bulk_cancel_event"].clear()
        try:
            ensured = _ensure_ebay_auth()
            if not ensured:
                _get_web_io().log("Authentication failed. Check credentials and try again.")
                _set_status("Attention", "Authentication failed. Check credentials.", "error")
                return
            os.makedirs("bulk_products", exist_ok=True)
            processed_count = 0
            total_items = len(prepared_items)
            for index, item in enumerate(prepared_items):
                display_index = item.get("index", index + 1)
                context["bulk_pause_event"].wait()
                if context["bulk_cancel_event"].is_set():
                    _get_web_io().log("Bulk process cancelled.")
                    _update_bulk_item(index, "Cancelled", "Cancelled before processing.")
                    for remaining_index in range(index + 1, total_items):
                        _update_bulk_item(remaining_index, "Cancelled", "Cancelled before processing.")
                    break
                _set_status("Working", f"Processing item {display_index} of {total_items}.", "working")
                _update_bulk_item(index, "Scraping", "Scraping Amazon listing.")
                _get_web_io().log(f"=== Processing Item {display_index}/{total_items} ===")
                product = scrape_amazon(
                    item.get("url", ""),
                    note=item.get("note", ""),
                    quantity=item.get("quantity", 1),
                    custom_specifics=item.get("custom_specifics", {}),
                    io=_get_web_io(),
                )
                if not product:
                    _get_web_io().log(f"Skipping item {display_index} due to scraping failure.")
                    _update_bulk_item(index, "Failed", "Scrape failed.")
                    continue
                with open(
                    os.path.join("bulk_products", f"product_{display_index}.json"),
                    "w",
                    encoding="utf-8",
                ) as handle:
                    json.dump(product, handle, indent=2)
                _update_bulk_item(index, "Listing", "Listing on eBay.")
                result = list_on_ebay(product, _get_web_io())
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
            if not context["bulk_cancel_event"].is_set():
                _get_web_io().log(f"Bulk processing finished. Processed {processed_count} items.")
                _set_status("Ready", "Bulk processing finished.", "success")
            else:
                _set_status("Attention", "Bulk processing cancelled.", "warning")
        finally:
            _update_bulk_state(running=False, paused=False, cancelled=context["bulk_cancel_event"].is_set())

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


@app.post("/api/bulk/pause")
def api_bulk_pause():
    if not _is_bulk_running():
        return jsonify({"ok": False, "error": "Bulk processing is not running."}), 400
    context = _get_user_context(g.user_id)
    if context["bulk_pause_event"].is_set():
        context["bulk_pause_event"].clear()
        _update_bulk_state(paused=True)
        _get_web_io().log("Bulk processing paused.")
        _set_status("Paused", "Bulk processing paused.", "warning")
        return jsonify({"ok": True, "paused": True})
    context["bulk_pause_event"].set()
    _update_bulk_state(paused=False)
    _get_web_io().log("Bulk processing resumed.")
    _set_status("Working", "Bulk processing resumed.", "working")
    return jsonify({"ok": True, "paused": False})


@app.post("/api/bulk/cancel")
def api_bulk_cancel():
    if not _is_bulk_running():
        return jsonify({"ok": False, "error": "Bulk processing is not running."}), 400
    context = _get_user_context(g.user_id)
    context["bulk_cancel_event"].set()
    if not context["bulk_pause_event"].is_set():
        context["bulk_pause_event"].set()
    _update_bulk_state(cancelled=True)
    _get_web_io().log("Cancellation requested...")
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
    run_web(host="0.0.0.0")