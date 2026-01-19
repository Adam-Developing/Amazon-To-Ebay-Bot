# tokens.py
from __future__ import annotations
import os
import json
import time
import base64
import threading
from typing import Optional
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import requests
from dotenv import load_dotenv
from ui_bridge import IOBridge

_ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=_ENV_PATH)
CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")
DEV_ID = os.getenv("EBAY_DEV_ID")
RUNAME = os.getenv("EBAY_RUNAME")
REDIRECT_URI_HOST = os.getenv("EBAY_REDIRECT_URI_HOST")  # The actual URL the RuName points to

user_SCOPES = "https://api.ebay.com/oauth/api_scope/sell.inventory https://api.ebay.com/oauth/api_scope/sell.marketing https://api.ebay.com/oauth/api_scope/sell.account https://api.ebay.com/oauth/api_scope/sell.fulfillment"
application_SCOPES = "https://api.ebay.com/oauth/api_scope"
TOKENS_FILE = "ebay_tokens.json"
API_ENDPOINT = "https://api.ebay.com/identity/v1/oauth2/token"

_OAUTH_CODE_LOCK = threading.Lock()
_OAUTH_CODE_EVENT = threading.Event()
_OAUTH_CODE_VALUE: Optional[str] = None
OAUTH_CODE_TIMEOUT_SECONDS = 600


def _reload_env() -> None:
    global CLIENT_ID, CLIENT_SECRET, DEV_ID, RUNAME, REDIRECT_URI_HOST
    load_dotenv(dotenv_path=_ENV_PATH, override=True)
    CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
    CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")
    DEV_ID = os.getenv("EBAY_DEV_ID")
    RUNAME = os.getenv("EBAY_RUNAME")
    REDIRECT_URI_HOST = os.getenv("EBAY_REDIRECT_URI_HOST")


def set_oauth_callback_code(code: str) -> None:
    """Allow external web servers to pass the OAuth code back to this module."""
    global _OAUTH_CODE_VALUE
    with _OAUTH_CODE_LOCK:
        _OAUTH_CODE_VALUE = code
        _OAUTH_CODE_EVENT.set()


def _wait_for_external_oauth_code(io: IOBridge) -> Optional[str]:
    """Block until an external callback provides the OAuth code."""
    global _OAUTH_CODE_VALUE
    io.log("Waiting for authorization code via web callback…")
    deadline = time.monotonic() + OAUTH_CODE_TIMEOUT_SECONDS
    while True:
        with _OAUTH_CODE_LOCK:
            if _OAUTH_CODE_VALUE:
                code = _OAUTH_CODE_VALUE
                _OAUTH_CODE_VALUE = None
                _OAUTH_CODE_EVENT.clear()
                return code
            _OAUTH_CODE_EVENT.clear()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            io.log("Timed out waiting for OAuth callback code.")
            return None
        _OAUTH_CODE_EVENT.wait(remaining)


def save_tokens(tokens, io: IOBridge):
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f, indent=4)
    io.log("Token data saved.")


def load_tokens():
    try:
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def clear_tokens(io: IOBridge) -> bool:
    """Delete the persisted token file to disconnect the eBay account.
    Returns True on success (or if nothing to delete), False on failure.
    """
    try:
        if os.path.exists(TOKENS_FILE):
            os.remove(TOKENS_FILE)
            io.log("Token file deleted.")
        else:
            io.log("No token file to delete.")
        return True
    except Exception as e:
        io.log(f"Failed to delete token file: {e}")
        return False


def clear_user_token(io: IOBridge) -> bool:
    """Remove only the user_token from the tokens file, preserving application_token."""
    try:
        tokens = load_tokens()
        if not tokens:
            io.log("No token file found; nothing to clear.")
            return True
        if 'user_token' in tokens:
            tokens.pop('user_token', None)
            with open(TOKENS_FILE, 'w') as f:
                json.dump(tokens, f, indent=4)
            io.log("User token removed.")
        else:
            io.log("No user token present; nothing to clear.")
        return True
    except Exception as e:
        io.log(f"Failed to clear user token: {e}")
        return False


def get_application_token(existing_tokens, io: IOBridge):
    io.log("Checking application token…")
    _reload_env()
    if not CLIENT_ID or not CLIENT_SECRET:
        io.log("Missing EBAY_CLIENT_ID or EBAY_CLIENT_SECRET. Update .env and restart the web server.")
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
    except requests.exceptions.RequestException as e:
        if getattr(e, "response", None) is not None and e.response.status_code == 401:
            io.log("Unauthorized application token. Verify EBAY_CLIENT_ID/EBAY_CLIENT_SECRET and keyset type.")
        io.log(f"Failed to get application token: {e.response.text if getattr(e, 'response', None) else str(e)}")
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
            # eBay requires scope(s) on refresh – must be a subset of originally granted scopes
            'scope': user_SCOPES
        }
        response = requests.post(API_ENDPOINT, headers=headers, data=body)
        response.raise_for_status()
        refreshed = response.json()
        refreshed['timestamp'] = time.time()

        # eBay usually does NOT return a new refresh_token on refresh.
        # Preserve the old refresh token + its expiry fields if missing.
        if 'refresh_token' not in refreshed:
            refreshed['refresh_token'] = refresh_token_value

        # If the server didn’t send refresh_token_expires_in this time, keep the old one if you have it.
        # (Handled in get_ebay_user_token when merging, see below.)
        return refreshed
    except requests.exceptions.RequestException as e:
        io.log(f"Failed to refresh user token: {e.response.text if getattr(e, 'response', None) else str(e)}")
        return None


def get_user_token_full_flow(io: IOBridge):
    _reload_env()
    auth_code = None
    server = None
    use_embedded_server = True

    class OAuthCallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal auth_code
            query_components = parse_qs(urlparse(self.path).query)
            if 'code' in query_components:
                auth_code = query_components["code"][0]
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"<h1>Authentication Successful!</h1><p>You can now close this browser window.</p>")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Authentication failed.")

    port = int(urlparse(REDIRECT_URI_HOST).port)
    try:
        server = HTTPServer(('', port), OAuthCallbackHandler)
    except OSError as exc:
        use_embedded_server = False
        io.log(
            f"OAuth callback port {port} is busy ({exc}). Ensure the web UI is running on "
            f"{REDIRECT_URI_HOST} so the /callback route can receive the consent response."
        )
    if use_embedded_server and server:
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()

    consent_url = f"https://auth.ebay.com/oauth2/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={RUNAME}&scope={user_SCOPES}"
    io.log("Opening browser for eBay consent…")
    io.open_url(consent_url)

    io.log("Waiting for authorization code…")
    if use_embedded_server and server:
        while not auth_code:
            time.sleep(0.5)
        server.shutdown()
    else:
        auth_code = _wait_for_external_oauth_code(io)
        if not auth_code:
            io.log("No authorization code received.")
            return None
    io.log("Authorization code received.")

    io.log("Exchanging authorization code for access token…")
    try:
        credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': f'Basic {encoded_credentials}'}
        body = {'grant_type': 'authorization_code', 'code': auth_code, 'redirect_uri': RUNAME}
        response = requests.post(API_ENDPOINT, headers=headers, data=body)
        response.raise_for_status()
        token_data = response.json()
        token_data['timestamp'] = time.time()
        return token_data
    except requests.exceptions.RequestException as e:
        io.log(f"Failed to get access token: {e.response.text if getattr(e, 'response', None) else str(e)}")
        return None


def get_ebay_user_token(existing_tokens, io: IOBridge):
    io.log("Checking user token…")
    user_token_data = existing_tokens.get('user_token', {})

    # Access token still valid?
    if user_token_data and time.time() < user_token_data.get('timestamp', 0) + user_token_data.get('expires_in', 0) - 300:
        io.log("Valid user token exists.")
        return user_token_data

    # Try refresh if we have a refresh_token
    if 'refresh_token' in user_token_data:
        refreshed = refresh_user_token(user_token_data['refresh_token'], io)
        if refreshed:
            # Preserve refresh-token fields if the refresh response didn’t include them
            if 'refresh_token_expires_in' not in refreshed and 'refresh_token_expires_in' in user_token_data:
                refreshed['refresh_token_expires_in'] = user_token_data['refresh_token_expires_in']
            if 'refresh_token' not in refreshed and 'refresh_token' in user_token_data:
                refreshed['refresh_token'] = user_token_data['refresh_token']
            io.log("User token refreshed and merged.")
            return refreshed
        io.log("Refresh failed; falling back to full login…")

    # No refresh token or refresh failed → full auth code flow
    return get_user_token_full_flow(io)
