from __future__ import annotations
import os
import json
import time
import base64
import threading
import tempfile
import hashlib
import stat
import getpass
import logging
import secrets
from typing import Optional, Dict
from urllib.parse import urlparse, parse_qs, quote

import requests
from dotenv import load_dotenv
from ui_bridge import IOBridge

_ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=_ENV_PATH)

# --- FIX: usage of .strip() ensures no accidental spaces from the .env file ---
CLIENT_ID = os.getenv("EBAY_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET", "").strip()
DEV_ID = os.getenv("EBAY_DEV_ID", "").strip()
RUNAME = os.getenv("EBAY_RUNAME", "").strip()
REDIRECT_URI_HOST = os.getenv("EBAY_REDIRECT_URI_HOST", "").strip()

user_SCOPES = "https://api.ebay.com/oauth/api_scope/sell.inventory https://api.ebay.com/oauth/api_scope/sell.marketing https://api.ebay.com/oauth/api_scope/sell.account https://api.ebay.com/oauth/api_scope/sell.fulfillment"
application_SCOPES = "https://api.ebay.com/oauth/api_scope"
TOKENS_FILE = "ebay_tokens.json"
API_ENDPOINT = "https://api.ebay.com/identity/v1/oauth2/token"

_OAUTH_CODE_LOCK = threading.Lock()
_OAUTH_CODE_EVENTS: Dict[str, threading.Event] = {}
_OAUTH_CODE_VALUES: Dict[str, str] = {}
OAUTH_CODE_TIMEOUT_SECONDS = 600
_LOGGER = logging.getLogger(__name__)
_OAUTH_FILE_LABEL = "amazon-to-ebay-oauth"
_OAUTH_FILE_FALLBACK_SALT = f"{getpass.getuser()}-{_OAUTH_FILE_LABEL}"


def _oauth_state_key(state: Optional[str]) -> str:
    return state or "default"


def _oauth_code_file_path(state: Optional[str] = None) -> str:
    salt = f"{_OAUTH_FILE_FALLBACK_SALT}-{_oauth_state_key(state)}"
    token = hashlib.sha256(salt.encode()).hexdigest()
    return os.path.join(tempfile.gettempdir(), f"amazon_to_ebay_oauth_{token}.txt")


def _get_oauth_event(state: Optional[str]) -> threading.Event:
    key = _oauth_state_key(state)
    event = _OAUTH_CODE_EVENTS.get(key)
    if not event:
        event = threading.Event()
        _OAUTH_CODE_EVENTS[key] = event
    return event


def _reload_env() -> None:
    global CLIENT_ID, CLIENT_SECRET, DEV_ID, RUNAME, REDIRECT_URI_HOST
    load_dotenv(dotenv_path=_ENV_PATH, override=True)
    CLIENT_ID = os.getenv("EBAY_CLIENT_ID", "").strip()
    CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET", "").strip()
    DEV_ID = os.getenv("EBAY_DEV_ID", "").strip()
    RUNAME = os.getenv("EBAY_RUNAME", "").strip()
    REDIRECT_URI_HOST = os.getenv("EBAY_REDIRECT_URI_HOST", "").strip()


def _poll_oauth_code(state: Optional[str] = None) -> Optional[str]:
    """Return any cached OAuth code and clear stale events. Caller must hold _OAUTH_CODE_LOCK."""
    key = _oauth_state_key(state)
    code = _OAUTH_CODE_VALUES.pop(key, None)
    if code:
        _get_oauth_event(state).clear()
        return code
    code_file = _oauth_code_file_path(state)
    if os.path.exists(code_file):
        try:
            mode = stat.S_IMODE(os.stat(code_file).st_mode)
            # Reject any group/other permissions and owner execute bit for safety.
            if mode & 0o177:
                _LOGGER.warning("OAuth code file permissions are insecure; ignoring file.")
                code = None
            else:
                with open(code_file, "r", encoding="utf-8") as handle:
                    code = handle.read().strip()
        except OSError:
            _LOGGER.warning("Failed to read OAuth code file.")
            code = None
        try:
            os.remove(code_file)
        except OSError:
            _LOGGER.warning("Failed to remove OAuth code file.")
        if code:
            _get_oauth_event(state).clear()
            return code
    event = _get_oauth_event(state)
    if event.is_set():
        event.clear()
    return None


def set_oauth_callback_code(code: str, state: Optional[str] = None) -> None:
    """Allow external web servers to pass the OAuth code back to this module."""
    with _OAUTH_CODE_LOCK:
        key = _oauth_state_key(state)
        _OAUTH_CODE_VALUES[key] = code
        _get_oauth_event(state).set()
        try:
            code_file = _oauth_code_file_path(state)
            for _ in range(2):
                try:
                    os.remove(code_file)
                except FileNotFoundError:
                    pass
                try:
                    fd = os.open(code_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    continue
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(code)
                break
            else:
                _LOGGER.warning("OAuth code file already exists; unable to write.")
        except OSError:
            _LOGGER.warning("Failed to write OAuth code file.")


def _ensure_tokens_dir() -> str:
    base_dir = os.getenv("AMAZON_TO_EBAY_TOKEN_DIR", os.getcwd())
    tokens_dir = os.path.join(base_dir, "user_tokens")
    os.makedirs(tokens_dir, exist_ok=True)
    return tokens_dir


def _tokens_file_for_user(user_id: Optional[str] = None) -> str:
    if not user_id:
        return TOKENS_FILE
    safe_id = quote(user_id, safe="")
    return os.path.join(_ensure_tokens_dir(), f"ebay_tokens_{safe_id}.json")


def save_tokens(tokens, io: IOBridge, user_id: Optional[str] = None):
    tokens_file = _tokens_file_for_user(user_id)
    with open(tokens_file, 'w', encoding="utf-8") as f:
        json.dump(tokens, f, indent=4)
    io.log("Token data saved.")


def load_tokens(user_id: Optional[str] = None):
    try:
        tokens_file = _tokens_file_for_user(user_id)
        with open(tokens_file, 'r', encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def clear_user_token(io: IOBridge, user_id: Optional[str] = None) -> bool:
    try:
        tokens = load_tokens(user_id)
        if not tokens:
            io.log("No token file found; nothing to clear.")
            return True
        if 'user_token' in tokens:
            tokens.pop('user_token', None)
            tokens_file = _tokens_file_for_user(user_id)
            with open(tokens_file, 'w', encoding="utf-8") as f:
                json.dump(tokens, f, indent=4)
            io.log("User token removed.")
        return True
    except Exception as e:
        io.log(f"Failed to clear user token: {e}")
        return False


def get_application_token(existing_tokens, io: IOBridge):
    io.log("Checking application token…")
    _reload_env()
    if not CLIENT_ID or not CLIENT_SECRET:
        io.log("Missing EBAY_CLIENT_ID or EBAY_CLIENT_SECRET.")
        return None
    app_token_data = existing_tokens.get('application_token', {})

    if app_token_data and time.time() < app_token_data.get('timestamp', 0) + app_token_data.get('expires_in', 0) - 300:
        io.log("Valid application token exists.")
        return app_token_data

    io.log("Requesting new application token…")
    try:
        credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': f'Basic {encoded_credentials}'}
        body = {'grant_type': 'client_credentials', 'scope': application_SCOPES}
        response = requests.post(API_ENDPOINT, headers=headers, data=body)
        response.raise_for_status()
        new_token_data = response.json()
        new_token_data['timestamp'] = time.time()
        io.log("New application token received.")
        return new_token_data
    except Exception as e:
        io.log(f"Failed to get application token: {e}")
        return None


def refresh_user_token(refresh_token_value, io: IOBridge):
    io.log("Refreshing user access token…")
    _reload_env()
    try:
        credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {encoded_credentials}'
        }
        body = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token_value,
            'scope': user_SCOPES
        }
        response = requests.post(API_ENDPOINT, headers=headers, data=body)
        response.raise_for_status()
        refreshed = response.json()
        refreshed['timestamp'] = time.time()

        if 'refresh_token' not in refreshed:
            refreshed['refresh_token'] = refresh_token_value

        return refreshed
    except Exception as e:
        io.log(f"Failed to refresh user token: {e}")
        return None


def get_user_token_full_flow(io: IOBridge, state: Optional[str] = None):
    _reload_env()
    auth_code = None

    state_value = state or secrets.token_urlsafe(24)
    consent_url = (
        "https://auth.ebay.com/oauth2/authorize"
        f"?client_id={CLIENT_ID}&response_type=code&redirect_uri={RUNAME}&scope={user_SCOPES}"
        f"&state={state_value}"
    )
    io.log("Opening browser for eBay consent…")
    io.open_url(consent_url)

    io.log("Waiting for authorization code (check your browser)…")

    # Polling loop waiting for Flask app to call set_oauth_callback_code
    deadline = time.monotonic() + OAUTH_CODE_TIMEOUT_SECONDS
    while not auth_code:
        with _OAUTH_CODE_LOCK:
            auth_code = _poll_oauth_code(state_value)

        if auth_code:
            break

        if time.monotonic() > deadline:
            io.log("Timed out waiting for code.")
            break

        time.sleep(1)

    if not auth_code:
    return None

    io.log("Authorization code received.")
    io.log("Exchanging code for access token…")
    try:
        credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': f'Basic {encoded_credentials}'}

        # We must send the code clean, and the redirect_uri must match exactly
        body = {
            'grant_type': 'authorization_code',
            'code': auth_code.strip(),
            'redirect_uri': RUNAME
        }

        response = requests.post(API_ENDPOINT, headers=headers, data=body)

        # --- DEBUG: Print the exact error if it fails ---
        if not response.ok:
            io.log(f"eBay Error Body: {response.text}")

        response.raise_for_status()
        token_data = response.json()
        token_data['timestamp'] = time.time()
        return token_data
    except Exception as e:
        io.log(f"Failed to get access token: {e}")
        return None


def get_ebay_user_token(existing_tokens, io: IOBridge, state: Optional[str] = None):
    io.log("Checking user token…")
    user_token_data = existing_tokens.get('user_token', {})

    if user_token_data and time.time() < user_token_data.get('timestamp', 0) + user_token_data.get('expires_in', 0) - 300:
        io.log("Valid user token exists.")
        return user_token_data

    if 'refresh_token' in user_token_data:
        refreshed = refresh_user_token(user_token_data['refresh_token'], io)
        if refreshed:
            if 'refresh_token' not in refreshed and 'refresh_token' in user_token_data:
                refreshed['refresh_token'] = user_token_data['refresh_token']
            io.log("User token refreshed.")
            return refreshed
        io.log("Refresh failed; falling back to login…")

    return get_user_token_full_flow(io, state=state)
