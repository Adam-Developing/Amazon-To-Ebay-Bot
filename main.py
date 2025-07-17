import subprocess
import sys
import os
import json
import time
import webbrowser
import base64
import requests
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")
DEV_ID = os.getenv("EBAY_DEV_ID")
# Use two separate variables for clarity and correctness
RUNAME = os.getenv("EBAY_RUNAME")
REDIRECT_URI_HOST = os.getenv("EBAY_REDIRECT_URI_HOST")  # The actual URL the RuName points to

user_SCOPES = "https://api.ebay.com/oauth/api_scope/sell.inventory https://api.ebay.com/oauth/api_scope/sell.marketing https://api.ebay.com/oauth/api_scope/sell.account https://api.ebay.com/oauth/api_scope/sell.fulfillment"
application_SCOPES = "https://api.ebay.com/oauth/api_scope"
TOKENS_FILE = "ebay_tokens.json"
API_ENDPOINT = "https://api.ebay.com/identity/v1/oauth2/token"


# --- Token Management ---

def save_tokens(tokens):
    """Saves the entire token dictionary to a file."""
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f, indent=4)
    print("✅ Token data saved successfully.")


def load_tokens():
    """Loads the entire token dictionary from a file."""
    try:
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_application_token(existing_tokens):
    """Gets a valid application token (Client Credentials Grant)."""
    print("\n--- Checking Application Token ---")
    app_token_data = existing_tokens.get('application_token', {})

    if app_token_data and time.time() < app_token_data.get('timestamp', 0) + app_token_data.get('expires_in', 0) - 300:
        print("✅ Valid application token already exists.")
        return app_token_data

    print("--- Requesting new application token... ---")
    try:
        credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': f'Basic {encoded_credentials}'}
        body = {'grant_type': 'client_credentials', 'scope': application_SCOPES}
        response = requests.post(API_ENDPOINT, headers=headers, data=body)
        response.raise_for_status()
        new_token_data = response.json()
        new_token_data['timestamp'] = time.time()
        print("✅ New application token received.")
        return new_token_data
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to get application token: {e.response.text if e.response else e}")
        return None


def refresh_user_token(refresh_token_value):
    """Exchanges a refresh token for a new user access token."""
    print("--- Refreshing expired user access token... ---")
    try:
        credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': f'Basic {encoded_credentials}'}
        body = {'grant_type': 'refresh_token', 'refresh_token': refresh_token_value, 'redirect_uri': RUNAME}
        response = requests.post(API_ENDPOINT, headers=headers, data=body)
        response.raise_for_status()
        new_token_data = response.json()
        new_token_data['timestamp'] = time.time()
        print("✅ New user token received via refresh.")
        return new_token_data
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to refresh user token: {e.response.text if e.response else e}")
        return None


def get_user_token_full_flow():
    """Starts the full user consent flow to get a new user token."""
    auth_code = None

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
    server = HTTPServer(('', port), OAuthCallbackHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    # The consent URL uses the RuName
    consent_url = f"https://auth.ebay.com/oauth2/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={RUNAME}&scope={user_SCOPES}"
    print("\n--- User Consent Required ---")
    print("Your browser will now open to grant permission to the application.")
    webbrowser.open(consent_url)

    print("\nWaiting for authorization code from eBay...")
    while not auth_code:
        time.sleep(1)
    server.shutdown()
    print("✅ Authorization code received.")

    print("--- Exchanging authorization code for access token... ---")
    try:
        credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': f'Basic {encoded_credentials}'}
        # The token exchange also uses the RuName
        body = {'grant_type': 'authorization_code', 'code': auth_code, 'redirect_uri': RUNAME}
        response = requests.post(API_ENDPOINT, headers=headers, data=body)
        response.raise_for_status()
        token_data = response.json()
        token_data['timestamp'] = time.time()
        return token_data
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to get access token: {e.response.text if e.response else e}")
        return None


def get_ebay_user_token(existing_tokens):
    """Main function to get a valid eBay user access token."""
    print("\n--- Checking User Token ---")
    user_token_data = existing_tokens.get('user_token', {})

    if user_token_data and time.time() < user_token_data.get('timestamp', 0) + user_token_data.get('expires_in',
                                                                                                   0) - 300:
        print("✅ Valid user token already exists.")
        return user_token_data

    if 'refresh_token' in user_token_data:
        return refresh_user_token(user_token_data['refresh_token'])

    return get_user_token_full_flow()


def run_script(script_name):
    """Runs a Python script, allowing for real-time interaction."""
    print(f"\n--- Running {script_name} ---")
    try:
        subprocess.run([sys.executable, script_name], check=True)
        print(f"--- Finished {script_name} successfully ---")
        return True
    except FileNotFoundError:
        print(f"❌ ERROR: The file '{script_name}' was not found.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR: {script_name} failed with exit code {e.returncode}.")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return False


def main():
    """Main function to orchestrate the process."""
    print("--- Starting Process ---")

    if not all([CLIENT_ID, CLIENT_SECRET, DEV_ID, RUNAME, REDIRECT_URI_HOST]):
        print("❌ ERROR: All eBay credentials must be set in the .env file.")
        return

    all_tokens = load_tokens()

    # Step 1: Get/Refresh Application Token
    app_token = get_application_token(all_tokens)
    if not app_token:
        print("Could not obtain eBay application token. Exiting.")
        return
    all_tokens['application_token'] = app_token
    save_tokens(all_tokens)

    # Step 2: Get/Refresh User Token
    user_token = get_ebay_user_token(all_tokens)
    if not user_token:
        print("Could not obtain eBay user token. Exiting.")
        return
    all_tokens['user_token'] = user_token
    save_tokens(all_tokens)

    print("\n--- All tokens are ready ---")
    for i in range(int(input("How many listings: "))):
        if run_script("amazon.py"):
            # If the first script was successful, run the second one
            run_script("ebay.py")


if __name__ == "__main__":
    main()
