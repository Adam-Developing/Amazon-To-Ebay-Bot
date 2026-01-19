# Amazon-To-Ebay Bot

An automated web application for scraping product information from Amazon UK and listing items on eBay with a browser-based UI. The application supports both single-item and bulk listing workflows with a built-in browser panel for authentication and verification.

## Features

- 🔍 **Amazon Product Scraping**: Automatically extracts product details, images, descriptions, and specifications from Amazon UK listings
- 📦 **eBay Listing Automation**: Creates complete eBay listings with proper category mapping, item specifics, and pricing
- 🖥️ **Web UI Interface**: Browser-based experience featuring an integrated browser panel for seamless OAuth authentication
- 📊 **Bulk Processing**: Process multiple products at once with pause/resume functionality
- 💰 **Smart Pricing**: Automatic price adjustments and eBay fee calculations
- 🔐 **Secure Authentication**: OAuth 2.0 integration with eBay APIs
- 🎨 **Custom Specifics**: Support for custom item attributes and seller notes
- 🌐 **Built-in Browser**: Tabbed in-app browsing with optional external Edge-style mode for Amazon and eBay pages

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [eBay Developer Setup](#ebay-developer-setup)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Usage Guide](#usage-guide)
- [Troubleshooting](#troubleshooting)
- [Technical Documentation](#technical-documentation)

## Prerequisites

Before installing the Amazon-To-Ebay Bot, ensure you have:

- **Python 3.10 or higher** installed on your system
- **Modern web browser** (Chrome, Edge, or Firefox recommended)
- **Internet connection** for API access and web scraping
- **eBay Developer Account** with active API credentials
- **Git** (optional, for cloning the repository)

## Installation

### Step 1: Clone or Download the Repository

```bash
# Using Git
git clone https://github.com/Adam-Developing/Amazon-To-Ebay-Bot.git
cd Amazon-To-Ebay-Bot

# Or download and extract the ZIP file from GitHub
```

### Step 2: Install Python Dependencies

Install all required packages using pip:

```bash
pip install -r requirements.txt
```

The application requires the following packages:
- `requests` - HTTP library for API calls and web scraping
- `beautifulsoup4` - HTML parsing for Amazon product pages
- `python-dotenv` - Environment variable management
- `Flask` - Web server for the browser-based UI

### Step 3: Verify Installation

Check that all dependencies are installed correctly:

```bash
python -c "import requests, bs4, dotenv, flask; print('All dependencies installed successfully!')"
```

## eBay Developer Setup

To use this application, you need eBay API credentials. Follow these steps:

### 1. Create an eBay Developer Account

1. Visit the [eBay Developers Program](https://developer.ebay.com/)
2. Click **"Register"** and create an account
3. Complete the registration process

### 2. Create an Application Keyset

1. Log in to the [eBay Developer Portal](https://developer.ebay.com/my/keys)
2. Navigate to **"Application Keysets"**
3. Click **"Create Application Keyset"**
4. Choose **"Production Keyset"** for live listings (or "Sandbox" for testing)
5. Fill in the application details:
   - **Application Title**: e.g., "Amazon to eBay Lister"
   - **Application Type**: "Server-to-Server & User Token"

### 3. Obtain Your API Credentials

After creating the keyset, you'll receive:
- **App ID (Client ID)**: Your application identifier
- **Cert ID (Client Secret)**: Your application secret key
- **Dev ID**: Your developer ID

**Important**: Keep these credentials secure and never share them publicly!

### 4. Create a RuName (Redirect URL Name)

1. In the eBay Developer Portal, go to **"User Tokens"** → **"Auth Accepted URL"**
2. Click **"Add Auth Accepted URL"**
3. Configure the redirect URL:
   - **Your privacy policy URL**: Your website or placeholder URL
   - **Your auth accepted URL**: `http://localhost:5000/callback`
4. Click **"Add"** and copy the generated **RuName**

### 5. Grant Application Permissions

Ensure your application has the following OAuth scopes enabled:
- `https://api.ebay.com/oauth/api_scope/sell.inventory`
- `https://api.ebay.com/oauth/api_scope/sell.marketing`
- `https://api.ebay.com/oauth/api_scope/sell.account`
- `https://api.ebay.com/oauth/api_scope/sell.fulfillment`

## Configuration

### Environment Variables Setup

1. Locate the `.env` file in the root directory of the application
2. Open it with a text editor and fill in your eBay credentials:

```bash
# eBay API Credentials (REQUIRED)
EBAY_CLIENT_ID=YourAppID_Here
EBAY_CLIENT_SECRET=YourCertID_Here
EBAY_DEV_ID=YourDevID_Here
EBAY_RUNAME=YourRuName_Here
EBAY_REDIRECT_URI_HOST=http://localhost:5000/callback

# Pricing Configuration
SELLER_PAY_FEE=True                    # Set to True if you want to calculate fees
EBAY_FIXED_FEE=0.72                    # Fixed eBay fee per listing (in GBP)
EBAY_BUYER_FIXED_FEE=0.72              # Alternative name for fixed fee

# Optional Settings
CUSTOM_SPECIFICS=False                  # Prompt for custom specifics during listing
DEFAULT_NEW_TAB_URL=https://www.google.com  # Default URL for new browser tabs
FLASK_SECRET_KEY=change-me              # Optional secret key for Flask session signing
```

### Configuration Options Explained

- **EBAY_CLIENT_ID**: Your App ID from the eBay Developer Portal
- **EBAY_CLIENT_SECRET**: Your Cert ID (keep this secret!)
- **EBAY_DEV_ID**: Your Developer ID
- **EBAY_RUNAME**: The RuName you created for OAuth redirects
- **EBAY_REDIRECT_URI_HOST**: Must match the redirect URL in your RuName (default: `http://localhost:5000/callback`)
- **SELLER_PAY_FEE**: If `True`, the app calculates the minimum price to cover eBay fees
- **EBAY_FIXED_FEE**: The fixed fee eBay charges per listing (adjust based on your region)
- **CUSTOM_SPECIFICS**: If `True`, prompts you to manually enter additional item specifics
- **FLASK_SECRET_KEY**: Optional secret key used to sign Flask session cookies (set it to keep sessions stable across restarts)

## Running the Application

### Start the Application

Run the main script:

```bash
python main.py
```

This will launch the web server. Open `http://localhost:5000` in your browser to access the interface:
- **Left Panel**: Controls for single/bulk listing
- **Right Panel**: Integrated browser panel for Amazon and eBay

### First-Time Setup: Authenticate with eBay

1. Click the **"Authorize eBay / Refresh Tokens"** button
2. The application will open a browser window to eBay's OAuth consent page
3. Log in with your eBay seller account
4. **Grant permissions** to the application
5. You'll be redirected back to `http://localhost:5000/callback`
6. The web app will display "Authentication Successful!"
7. Tokens are automatically saved to `ebay_tokens.json`

**Note**: Tokens are refreshed automatically. Re-authorize if you see authentication errors.

## Usage Guide

### Single Item Listing

1. **Enter Amazon URL**:
   - Paste an Amazon UK product URL in the "Amazon URL" field
   - Example: `https://www.amazon.co.uk/dp/B08N5WRWNW`

2. **Set Quantity and Note** (optional):
   - Enter the quantity you want to list
   - Add a private seller note (visible only to you on eBay)

3. **Add Custom Specifics** (optional):
   - Format: `Size: XL | Colour: Black | Material: Cotton`
   - Separate multiple attributes with `|`

4. **Scrape Amazon**:
   - Click **"Scrape Amazon"**
   - The app fetches product details, images, and descriptions
   - Review the log for any issues

5. **List on eBay**:
   - Click **"List on eBay"**
   - The app creates the listing with auto-filled categories and specifics
   - A browser tab opens to the eBay revise page for final adjustments
   - The Item ID is logged for your records

### Bulk Listing

1. Switch to the **"Bulk"** tab

2. **Prepare Bulk Text**:
   Paste your bulk data in the following format:

   ```
   https://www.amazon.co.uk/dp/B08N5WRWNW
   Quantity: 2
   Note: Gift item
   Size: Large | Colour: Blue

   https://www.amazon.co.uk/dp/B07XYZ1234
   Quantity: 1
   Note: Clearance sale
   Style: Modern | Material: Wood

   https://www.amazon.co.uk/dp/B09ABC5678
   ```

   **Format Rules**:
   - Each item separated by a blank line or standalone number
   - Amazon URL (required)
   - `Quantity: N` (optional, defaults to 1)
   - `Note: Your note` (optional)
   - Custom specifics: `Key: Value | Key: Value` (optional)

3. **Process Bulk**:
   - Click **"Process Bulk"**
   - The app processes each item sequentially
   - Use **"Pause"** to temporarily stop
   - Use **"Cancel"** to abort the entire batch

4. **Review Results**:
   - Completed products are saved to `bulk_products/product_N.json`
   - Check the log for success/failure status

### Load Product from JSON

If you've previously scraped a product:

1. Click **"Load from JSON..."**
2. Select a saved `.json` file (e.g., `product.json` or `bulk_products/product_1.json`)
3. The product data is loaded, and you can directly click **"List on eBay"**

### Browser Features

- **Navigation**: Use Back (◀), Forward (▶), and Refresh (⟳) buttons
- **Address Bar**: Enter URLs or search terms (automatically uses Google)
- **New Tabs**: Click the `+` tab or press `Ctrl+T`
- **Close Tabs**: Click the `X` on any tab or press `Ctrl+W`
- **Edge Mode**: Check "Edge mode" to open links in Microsoft Edge (Windows only)
- **Keyboard Shortcuts**:
  - `Ctrl+Tab` / `Ctrl+Shift+Tab`: Switch between tabs
  - `F5` / `Ctrl+R`: Reload page
  - `Alt+Left` / `Alt+Right`: Navigate back/forward
  - `Ctrl+T`: New tab
  - `Ctrl+W`: Close current tab

### Logout from eBay

To disconnect your eBay account:

1. Click **"Logout eBay"**
2. Confirm the action
3. Your user token is removed (application token is preserved)
4. Re-authorize when you want to reconnect

## Troubleshooting

### Common Issues

#### "Token file is missing or malformed"
- **Solution**: Click "Authorize eBay / Refresh Tokens" to authenticate
- Ensure your `.env` file has correct credentials

#### "Failed to get application token"
- **Solution**: Verify your `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` in `.env`
- Check that your eBay Developer Account is active

#### "Price is N/A" or "-1.0"
- **Solution**: The app couldn't find the price on Amazon
- You'll be prompted to enter the price manually
- Ensure the Amazon URL is valid and accessible

#### "Title is N/A"
- **Solution**: The Amazon page structure may have changed
- You'll be prompted to enter the title manually
- Open the Amazon page in the browser to verify

#### Scraping returns empty or incomplete data
- **Cause**: Amazon may have updated their HTML structure
- **Solution**: Update the parsing logic in `amazon.py` or report an issue

#### Authentication redirects fail
- **Solution**: Ensure `EBAY_REDIRECT_URI_HOST` matches your RuName's redirect URL
- Check that port 5000 is not blocked by a firewall
- Try changing the port in both `.env` and your RuName configuration

#### Embedded browser panel not loading a site
- The embedded browser panel has been removed from the web UI.
- Links now open directly in a new browser tab to avoid iframe blocking.

#### Import errors (missing modules)
- **Solution**: Reinstall dependencies: `pip install -r requirements.txt`
- Use a virtual environment to avoid conflicts

### Debug Mode

To enable detailed logging:
1. Open `web_app.py`
2. Look for log statements and review console output
3. Check `website.html` (saved during scraping) for raw Amazon page data

### Log Files

- **ebay_tokens.json**: Stores OAuth tokens (do not share!)
- **product.json**: Last scraped single product
- **bulk_products/**: Folder with bulk scraped products
- **website.html**: Raw Amazon page HTML (for debugging)

## Technical Documentation

### Architecture Overview

The application follows a modular architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                      Web Layer (web_app.py)                 │
│  - Flask UI: Routes, prompts, log streaming, browser panel  │
│  - Event handlers: Button clicks, keyboard shortcuts        │
│  - Threading: Separate threads for blocking operations      │
└────────────────┬────────────────────────────────────────────┘
                 │
      ┌──────────┴──────────┐
      │                     │
┌─────▼─────┐       ┌───────▼────────┐
│  Bridge   │       │   Core Logic   │
│ ui_bridge │       │                │
│   .py     │       │  • amazon.py   │
└───────────┘       │  • ebay.py     │
                    │  • tokens.py   │
                    │  • bulk_parser │
                    │  • CentralFuns │
                    └────────────────┘
```

### File Structure and Functions

#### `main.py` (Entry Point)
**Purpose**: Application entry point that launches the web server.

**Functions**:
- `if __name__ == "__main__"`: Calls `run_web()` to start the application

**Location**: Root directory

---

#### `web_app.py` (Web UI and Application Logic)
**Purpose**: Contains the Flask-based web interface, event handlers, and threading logic.

**Key Components**:

1. **`WebIOBridge(IOBridge)`**
   - Bridges console I/O with web prompts, logs, and URL opening
   - Thread-safe queueing for prompts and browser events

2. **Flask Routes**
   - `/` serves the web interface
   - `/api/*` endpoints drive scraping, listing, bulk processing, and logging
   - `/callback` handles OAuth redirects for eBay consent

3. **Browser Panel**
   - Managed in `static/app.js` with tab controls and navigation buttons
   - Edge mode opens URLs in a new browser tab

**Location**: Root directory

---

#### `amazon.py` (Amazon Product Scraping)
**Purpose**: Scrapes product information from Amazon UK product pages.

**Key Functions**:

- **`scrape_amazon(url, note, quantity, custom_specifics, io)`** (Line 133)
  - **Main entry point** for scraping
  - Downloads and parses Amazon product page
  - Returns a dictionary with product data
  - **Parameters**:
    - `url`: Amazon product URL
    - `note`: Optional seller note
    - `quantity`: Optional quantity override
    - `custom_specifics`: Dict of custom item specifics
    - `io`: IOBridge instance for logging
  - **Returns**: Product dictionary with keys:
    - `Title`, `Price`, `URL`, `imageUrls`
    - `prodDetails`, `productOverview`, `featuredBullets`, `detailBullets`
    - `importantInformation`, `tempDeal`, `discount_type`, `discount_value`
    - `customSpecifics`, `sellerNote`, `quantity`

- **`get_image_urls(soup)`** (Line 75)
  - Extracts high-resolution product images from Amazon's JavaScript data
  - Returns list of image URLs

- **`get_product_overview(page, id)`** (Line 117)
  - Parses product overview table
  - Returns dict of key-value pairs

- **`get_info(page, ids)`** (Line 104)
  - Extracts product details from various table formats
  - Tries multiple table IDs (`prodDetails`, `tech`)
  - Returns dict of specifications

- **`handle_table(page, id)`** (Line 23): Parses standard product details table
- **`handle_alt_table(page, id)`** (Line 34): Parses alternative table format
- **`handle_list(page, id)`** (Line 47): Parses list-based product details
- **`handle_html_content(page, id)`** (Line 70): Extracts raw HTML content

**Global Variables**:
- `headers`: HTTP headers for Amazon requests (mimics Firefox browser)
- `IGNORED_KEYS`: Set of keys to ignore (ASIN, reviews, rank, etc.)

**Location**: Root directory

---

#### `ebay.py` (eBay Listing Creation)
**Purpose**: Creates eBay listings using the Trading API (XML-based).

**Key Functions**:

- **`list_on_ebay(data, io)`** (Line 61)
  - **Main entry point** for listing on eBay
  - Builds XML request for `AddItem` API call
  - Handles category discovery, item specifics, pricing, and images
  - Opens eBay revise page after successful listing
  - **Parameters**:
    - `data`: Product dictionary from `scrape_amazon()`
    - `io`: IOBridge instance
  - **Returns**: Result dict with keys:
    - `ok`: Boolean success status
    - `item_id`: eBay item ID (if successful)
    - `ack`: API acknowledgment status
    - `status`: HTTP status code
    - `response`: Raw XML response

- **`_sanitize_text_block(text)`** (Line 40)
  - Removes sentences containing banned phrases (warranty, customer service, Amazon, etc.)
  - Used to clean descriptions before listing

- **`esc_xml(s)`** (Line 57)
  - Escapes XML special characters (`&`, `<`, `>`)

**Global Variables**:
- `BANNED_PHRASES`: List of regex patterns for prohibited content
- `_BANNED_RE`: Compiled regex for banned phrases
- `_SENTENCE_SPLIT_RE`: Regex for sentence splitting

**API Interaction**:
- Endpoint: `https://api.ebay.com/ws/api.dll`
- API Call: `AddItem`
- Site ID: `3` (UK)
- Compatibility Level: `967`

**Location**: Root directory

---

#### `tokens.py` (eBay OAuth Token Management)
**Purpose**: Handles eBay OAuth 2.0 authentication and token lifecycle.

**Key Functions**:

- **`get_application_token(existing_tokens, io)`** (Line 78)
  - Fetches or refreshes eBay application-level (public) token
  - Uses client credentials grant type
  - Returns token dict with `access_token`, `expires_in`, `timestamp`

- **`get_ebay_user_token(existing_tokens, io)`** (Line 186)
  - Fetches or refreshes eBay user token (seller authorization)
  - Checks token validity, attempts refresh, or triggers full OAuth flow
  - Returns token dict with `access_token`, `refresh_token`, etc.

- **`refresh_user_token(refresh_token_value, io)`** (Line 103)
  - Refreshes an expired user access token using the refresh token
  - Preserves refresh token if eBay doesn't return a new one

- **`get_user_token_full_flow(io)`** (Line 136)
  - Performs full OAuth 2.0 authorization code flow
  - Uses the `/callback` web route (or embedded server if needed) for the redirect
  - Opens browser for user consent
  - Exchanges authorization code for tokens

- **`save_tokens(tokens, io)`** (Line 28)
  - Saves token dict to `ebay_tokens.json`

- **`load_tokens()`** (Line 34)
  - Loads tokens from `ebay_tokens.json`
  - Returns empty dict if file doesn't exist

- **`clear_tokens(io)`** (Line 42)
  - Deletes the entire token file (logs out completely)

- **`clear_user_token(io)`** (Line 58)
  - Removes only the user token, keeping application token

**Global Variables**:
- `CLIENT_ID`, `CLIENT_SECRET`, `DEV_ID`: eBay API credentials from `.env`
- `RUNAME`: OAuth redirect URL name
- `REDIRECT_URI_HOST`: Local callback URL (default: `http://localhost:5000/callback`)
- `user_SCOPES`: OAuth scopes for user token
- `application_SCOPES`: OAuth scopes for application token
- `TOKENS_FILE`: Filename for token storage (`ebay_tokens.json`)

**Location**: Root directory

---

#### `CentralFunctions.py` (Shared Utilities)
**Purpose**: Provides utility functions for eBay category discovery, item specifics, pricing, and aspect name mapping.

**Key Functions**:

- **`get_item_specifics(token, category_tree_id, category_id, product_data, io)`** (Line 154)
  - Fetches eBay taxonomy for the category
  - Merges scraped data with user-provided custom specifics
  - Prompts user for required/missing aspects
  - Validates selection-only aspects against allowed values
  - **Returns**: Dict of item specifics ready for eBay listing

- **`categoryTreeID(access_token)`** (Line 90)
  - Fetches the default category tree ID for eBay GB marketplace
  - Defaults to `3` on error

- **`categoryID(access_token, categoryTreeId, title_variable)`** (Line 123)
  - Suggests eBay category ID based on product title
  - Uses eBay Taxonomy API's `get_category_suggestions`
  - Defaults to `14254` (general category) on error

- **`set_seller_note(item_id, note, user_token, app_id, dev_id, cert_id, io)`** (Line 277)
  - Sets a private seller note on an existing eBay item
  - Uses `SetUserNotes` Trading API call

- **`map_to_ebay_aspect_name(input_key)`** (Line 57)
  - Maps common aspect names to eBay's exact aspect names
  - Case-insensitive matching with normalization
  - Returns exact eBay aspect name or `None`

- **`map_one_dict(d)`** (Line 69)
  - Maps all keys in a dict using `map_to_ebay_aspect_name`
  - Keeps original key if no mapping exists

- **`merge_specifics_in_order(*dicts)`** (Line 77)
  - Merges multiple specifics dicts with later dicts overriding earlier ones
  - Case-sensitive comparison (eBay aspect names are case-sensitive)

- **`calculate_ebay_fee(item_price)`** (Line 330)
  - Calculates eBay selling fees based on tiered structure
  - Fixed fee + variable fee (4% up to £300, 2% above)

- **`find_minimum_price(target_total)`** (Line 354)
  - Calculates minimum item price to reach target total after fees
  - Iterative penny-by-penny search

**Global Variables**:
- `EBAY_ASPECT_KEY_MAP`: Dict mapping common names to exact eBay aspect names
- `FIXED_FEE`: eBay fixed fee per listing (from `.env`)

**Helper Functions**:
- **`_norm(s)`** (Line 49): Normalizes strings for aspect name comparison

**Location**: Root directory

---

#### `bulk_parser.py` (Bulk Text Parsing)
**Purpose**: Parses bulk text input into structured item data for batch processing.

**Key Functions**:

- **`parse_bulk_items(text)`** (Line 34)
  - Parses multi-line bulk text into list of item dicts
  - Splits on blank lines or standalone numbers
  - Extracts URL, quantity, note, and custom specifics per item
  - **Returns**: List of dicts with keys:
    - `url`: Amazon URL
    - `quantity`: Item quantity (default: 1)
    - `note`: Seller note
    - `custom_specifics`: Dict of custom specifics

- **`_parse_specifics_line(line)`** (Line 17)
  - Parses a line like `Size: Large | Colour: Blue`
  - Returns dict of key-value pairs
  - Only recognizes common spec keys to avoid false positives

**Global Variables**:
- `COMMON_SPEC_KEYS`: Set of recognized custom specific keys
- `_url_re`, `_qty_re`, `_note_re`: Compiled regex patterns

**Location**: Root directory

---

#### `ui_bridge.py` (UI Abstraction)
**Purpose**: Provides an abstract interface for UI interactions (logging, prompts, URL opening).

**Key Classes**:

- **`IOBridge`** (Line 6)
  - Base class with default no-op implementations
  - Methods:
    - **`log(msg)`**: Logs a message (default: silent)
    - **`prompt_text(prompt, default)`**: Prompts for text input (default: returns default)
    - **`prompt_choice(prompt, options)`**: Prompts for choice (default: returns first option)
    - **`open_url(url)`**: Opens URL in browser (default: uses `webbrowser.open()`)

**Usage**:
- The web UI subclasses `IOBridge` via `WebIOBridge` to provide interactive prompts and logging
- Core logic functions accept `IOBridge` to remain UI-agnostic

**Location**: Root directory

---

### Data Flow

1. **Single Item Workflow**:
   ```
   User enters Amazon URL
     ↓
   on_scrape() → scrape_amazon() [amazon.py]
     ↓
   Product dict saved → product.json
     ↓
   on_list() → list_on_ebay() [ebay.py]
     ↓
   eBay API: AddItem request
     ↓
   Success: Open eBay revise page
   ```

2. **Bulk Workflow**:
   ```
   User pastes bulk text
     ↓
   parse_bulk_items() [bulk_parser.py]
     ↓
   For each item:
     - scrape_amazon() [amazon.py]
     - Save to bulk_products/product_N.json
     - list_on_ebay() [ebay.py]
   ```

3. **Authentication Workflow**:
   ```
   User clicks "Authorize eBay"
     ↓
   get_application_token() [tokens.py]
     ↓
   get_ebay_user_token() [tokens.py]
     ↓
   OAuth consent flow → Authorization code
     ↓
   Exchange code for tokens → Save to ebay_tokens.json
   ```

### Key Technologies

- **Flask**: Python web server for the browser-based UI
- **HTML/CSS/JavaScript**: Frontend for the in-browser controls and browser panel
- **Beautiful Soup 4**: HTML parsing for web scraping
- **Requests**: HTTP client for API calls
- **eBay APIs**:
  - **Trading API** (XML): Legacy API for listing items (`AddItem`, `SetUserNotes`)
  - **Taxonomy API** (REST): Category and item specifics discovery
  - **OAuth 2.0**: Authentication and authorization

### API Endpoints

- **eBay Trading API**: `https://api.ebay.com/ws/api.dll`
- **eBay Taxonomy API**: `https://api.ebay.com/commerce/taxonomy/v1/`
- **eBay OAuth**: `https://api.ebay.com/identity/v1/oauth2/token`
- **eBay OAuth Consent**: `https://auth.ebay.com/oauth2/authorize`

### Threading Model

- **Main Thread**: Flask web server request handling
- **Worker Threads**: Created for blocking operations (scraping, listing, authentication)
- **Shared State**: Locked in-memory structures for logs, prompts, and bulk progress

### File Outputs

- **ebay_tokens.json**: OAuth tokens (application + user)
- **product.json**: Last scraped single product
- **bulk_products/product_N.json**: Bulk scraped products
- **website.html**: Debug HTML from Amazon page

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request with a clear description

## License

This project is provided as-is for educational and personal use. Ensure compliance with Amazon's and eBay's terms of service when using automated tools.

## Disclaimer

This application automates interactions with Amazon and eBay. Use responsibly and in accordance with both platforms' terms of service. The authors are not responsible for any misuse or violations.

## Support

For issues, questions, or feature requests:
- Open an issue on [GitHub](https://github.com/Adam-Developing/Amazon-To-Ebay-Bot/issues)
- Check the [Troubleshooting](#troubleshooting) section first

## Changelog

**v2.0** (Current)
- Web-based UI with embedded browser panel
- Single and bulk listing support
- OAuth 2.0 integration
- Automatic category and specifics mapping

---

**Happy Listing! 🚀**
