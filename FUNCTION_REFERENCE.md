# Function Reference Guide

Quick reference for finding specific functions in the Amazon-To-Ebay Bot codebase.

## Quick Function Finder

### Amazon Scraping Functions (amazon.py)

| Function | Line | Purpose |
|----------|------|---------|
| `scrape_amazon()` | 133 | Main entry point for scraping Amazon product pages |
| `get_image_urls()` | 75 | Extracts high-resolution product images |
| `get_product_overview()` | 117 | Parses product overview table |
| `get_info()` | 104 | Extracts product details from tables |
| `handle_table()` | 23 | Parses standard product details table |
| `handle_alt_table()` | 34 | Parses alternative table format |
| `handle_list()` | 47 | Parses list-based product details |
| `handle_html_content()` | 70 | Extracts raw HTML content |

### eBay Listing Functions (ebay.py)

| Function | Line | Purpose |
|----------|------|---------|
| `list_on_ebay()` | 61 | Main entry point for creating eBay listings |
| `_sanitize_text_block()` | 40 | Removes banned phrases from descriptions |
| `esc_xml()` | 57 | Escapes XML special characters |

### Token Management Functions (tokens.py)

| Function | Line | Purpose |
|----------|------|---------|
| `get_application_token()` | 78 | Fetches/refreshes eBay application token |
| `get_ebay_user_token()` | 186 | Fetches/refreshes eBay user token |
| `refresh_user_token()` | 103 | Refreshes expired user access token |
| `get_user_token_full_flow()` | 136 | Performs full OAuth 2.0 authorization flow |
| `save_tokens()` | 28 | Saves tokens to ebay_tokens.json |
| `load_tokens()` | 34 | Loads tokens from ebay_tokens.json |
| `clear_tokens()` | 42 | Deletes entire token file |
| `clear_user_token()` | 58 | Removes only user token |

### Central Utility Functions (CentralFunctions.py)

| Function | Line | Purpose |
|----------|------|---------|
| `get_item_specifics()` | 154 | Fetches and maps eBay item specifics |
| `categoryTreeID()` | 90 | Gets default category tree ID for eBay GB |
| `categoryID()` | 123 | Suggests eBay category ID from title |
| `set_seller_note()` | 277 | Sets private seller note on eBay item |
| `map_to_ebay_aspect_name()` | 57 | Maps aspect names to eBay's exact names |
| `map_one_dict()` | 69 | Maps all keys in a dict |
| `merge_specifics_in_order()` | 77 | Merges multiple specifics dicts |
| `calculate_ebay_fee()` | 330 | Calculates eBay selling fees |
| `find_minimum_price()` | 354 | Calculates minimum price to cover fees |
| `_norm()` | 49 | Normalizes strings for comparison |

### Bulk Parsing Functions (bulk_parser.py)

| Function | Line | Purpose |
|----------|------|---------|
| `parse_bulk_items()` | 34 | Parses bulk text into structured item data |
| `_parse_specifics_line()` | 17 | Parses custom specifics line |

### Web UI Functions (web_app.py)

| Function | Line | Purpose |
|----------|------|---------|
| `run_web()` | 465 | Starts the Flask web server |
| `api_state()` | 200 | Returns UI state for button enablement |
| `api_logs()` | 211 | Streams log entries to the browser |
| `api_prompts()` | 229 | Returns pending prompts for user input |
| `api_load_json()` | 252 | Loads product JSON into the UI |
| `api_scrape()` | 319 | Starts Amazon scraping in a worker thread |
| `api_list()` | 356 | Starts eBay listing in a worker thread |
| `api_bulk_process()` | 384 | Starts bulk processing workflow |
| `api_bulk_pause()` | 439 | Pauses or resumes bulk processing |
| `api_bulk_cancel()` | 454 | Cancels bulk processing |
| `oauth_callback()` | 191 | Handles OAuth redirect back to the web app |

### UI Bridge Functions (ui_bridge.py)

| Function | Line | Purpose |
|----------|------|---------|
| `log()` | 11 | Logs a message (override in subclass) |
| `prompt_text()` | 14 | Prompts for text input (override in subclass) |
| `prompt_choice()` | 17 | Prompts for choice (override in subclass) |
| `open_url()` | 20 | Opens URL in browser |

## Common Tasks and Where to Find Them

### To modify Amazon scraping logic:
- **File**: `amazon.py`
- **Main function**: `scrape_amazon()` (line 133)
- **Image extraction**: `get_image_urls()` (line 75)
- **Product details**: `get_info()` (line 104)

### To modify eBay listing logic:
- **File**: `ebay.py`
- **Main function**: `list_on_ebay()` (line 61)
- **Description sanitization**: `_sanitize_text_block()` (line 40)
- **Category mapping**: Uses `CentralFunctions.categoryID()` (line 123)

### To modify authentication flow:
- **File**: `tokens.py`
- **OAuth flow**: `get_user_token_full_flow()` (line 136)
- **Token refresh**: `refresh_user_token()` (line 103)
- **Token storage**: `save_tokens()` (line 28), `load_tokens()` (line 34)

### To modify item specifics mapping:
- **File**: `CentralFunctions.py`
- **Mapping dict**: `EBAY_ASPECT_KEY_MAP` (lines 14-47)
- **Mapping function**: `map_to_ebay_aspect_name()` (line 57)
- **Specifics fetching**: `get_item_specifics()` (line 154)

### To modify bulk text parsing:
- **File**: `bulk_parser.py`
- **Main function**: `parse_bulk_items()` (line 34)
- **Specifics parsing**: `_parse_specifics_line()` (line 17)
- **Common keys**: `COMMON_SPEC_KEYS` (lines 5-11)

### To modify web UI layout or behavior:
- **Backend routes**: `web_app.py`
- **HTML structure**: `templates/index.html`
- **Browser panel logic**: `static/app.js`
- **Styling**: `static/styles.css`

### To modify pricing calculations:
- **File**: `CentralFunctions.py`
- **Fee calculation**: `calculate_ebay_fee()` (line 330)
- **Price optimization**: `find_minimum_price()` (line 354)
- **Fixed fee setting**: `.env` file, `EBAY_FIXED_FEE` variable

### To add new eBay aspect mappings:
1. Open `CentralFunctions.py`
2. Edit `EBAY_ASPECT_KEY_MAP` dictionary (lines 14-47)
3. Add entries in format: `"input_name": "Exact eBay Aspect Name"`
4. Left side is case-insensitive input, right side must match eBay's exact name

### To modify banned phrases in descriptions:
1. Open `ebay.py`
2. Edit `BANNED_PHRASES` list (lines 24-30)
3. Add regex patterns for phrases to remove from listings

## File Hierarchy

```
Amazon-To-Ebay-Bot/
├── main.py                  # Entry point (5 lines)
├── web_app.py               # Web application (471 lines)
├── gui.py                   # Legacy GUI application (1306 lines)
├── amazon.py                # Amazon scraping (247 lines)
├── ebay.py                  # eBay listing (344 lines)
├── tokens.py                # OAuth management (210 lines)
├── CentralFunctions.py      # Utilities (395 lines)
├── bulk_parser.py           # Bulk parsing (87 lines)
├── ui_bridge.py             # UI abstraction (26 lines)
├── templates/               # HTML templates
├── static/                  # Web UI assets (JS/CSS)
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables
├── webview.qml              # QML web view component
├── README.md                # Main documentation (768 lines)
└── FUNCTION_REFERENCE.md    # This file
```

## Data Structures

### Product Dictionary (returned by scrape_amazon)
```python
{
    'Title': str,                    # Product title
    'Price': float,                  # Product price (or -1.0 if not found)
    'URL': str,                      # Amazon product URL
    'imageUrls': [str],              # List of high-res image URLs
    'prodDetails': {str: str},       # Technical specifications
    'productOverview': {str: str},   # Product overview table
    'featuredBullets': [str],        # Bullet point features
    'detailBullets': {str: str},     # Additional detail bullets
    'importantInformation': str,     # Important info HTML
    'tempDeal': bool,                # Whether product has a deal badge
    'discount_type': str,            # 'percentage' or 'fixed'
    'discount_value': float,         # Discount amount
    'customSpecifics': {str: str},   # Custom item specifics
    'sellerNote': str,               # Private seller note
    'quantity': int                  # Listing quantity
}
```

### Bulk Item Dictionary (returned by parse_bulk_items)
```python
{
    'url': str,                      # Amazon URL
    'quantity': int,                 # Quantity (default: 1)
    'note': str,                     # Seller note
    'custom_specifics': {str: str}   # Custom item specifics
}
```

### Token Dictionary (stored in ebay_tokens.json)
```python
{
    'application_token': {
        'access_token': str,
        'token_type': str,
        'expires_in': int,
        'timestamp': float
    },
    'user_token': {
        'access_token': str,
        'refresh_token': str,
        'token_type': str,
        'expires_in': int,
        'refresh_token_expires_in': int,
        'timestamp': float
    }
}
```

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `EBAY_CLIENT_ID` | Yes | - | eBay App ID (Client ID) |
| `EBAY_CLIENT_SECRET` | Yes | - | eBay Cert ID (Client Secret) |
| `EBAY_DEV_ID` | Yes | - | eBay Developer ID |
| `EBAY_RUNAME` | Yes | - | eBay RuName (OAuth redirect) |
| `EBAY_REDIRECT_URI_HOST` | No | `http://localhost:5000/callback` | OAuth callback URL |
| `SELLER_PAY_FEE` | No | `True` | Calculate fees in pricing |
| `EBAY_FIXED_FEE` | No | `0.72` | Fixed fee per listing (GBP) |
| `EBAY_BUYER_FIXED_FEE` | No | `0.72` | Alternative name for fixed fee |
| `CUSTOM_SPECIFICS` | No | `False` | Prompt for custom specifics |
| `DEFAULT_NEW_TAB_URL` | No | `https://www.google.com` | Default URL for new tabs |

## API Endpoints Used

### eBay Trading API (XML)
- **Endpoint**: `https://api.ebay.com/ws/api.dll`
- **Calls**: `AddItem`, `SetUserNotes`
- **Site ID**: `3` (UK)

### eBay Taxonomy API (REST)
- **Base**: `https://api.ebay.com/commerce/taxonomy/v1/`
- **Endpoints**:
  - `get_default_category_tree_id`
  - `category_tree/{id}/get_category_suggestions`
  - `category_tree/{id}/get_item_aspects_for_category`

### eBay OAuth API
- **Token Endpoint**: `https://api.ebay.com/identity/v1/oauth2/token`
- **Authorize Endpoint**: `https://auth.ebay.com/oauth2/authorize`

---

*This reference guide corresponds to the codebase as of the latest commit. Line numbers may change as code evolves.*
