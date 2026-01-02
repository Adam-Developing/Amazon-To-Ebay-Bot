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

### GUI Functions (gui.py)

#### Main Window Functions

| Function | Line | Purpose |
|----------|------|---------|
| `__init__()` | 268 | Initializes main window UI |
| `on_auth()` | 903 | Handles eBay OAuth authentication |
| `on_logout()` | 926 | Logs out from eBay |
| `on_scrape()` | 955 | Scrapes Amazon product |
| `_on_scrape_done()` | 986 | Callback after scraping completes |
| `on_list()` | 1024 | Lists product on eBay |
| `_on_list_done()` | 1070 | Callback after listing completes |
| `on_process_bulk()` | 1076 | Processes bulk items |
| `on_bulk_pause_resume()` | 1046 | Pauses/resumes bulk processing |
| `on_bulk_cancel()` | 1056 | Cancels bulk processing |
| `on_load_json()` | 885 | Loads product from JSON file |

#### Browser Functions

| Function | Line | Purpose |
|----------|------|---------|
| `create_browser_tab()` | 510 | Creates new browser tab |
| `on_close_tab()` | 541 | Closes browser tab |
| `navigate_current()` | 738 | Navigates current tab to URL |
| `on_addr_enter()` | 670 | Handles address bar Enter key |
| `on_back()` | 1180 | Browser back navigation |
| `on_forward()` | 1188 | Browser forward navigation |
| `on_reload()` | 1196 | Reloads current page |
| `_on_view_url_changed()` | 525 | Updates UI when URL changes |
| `_update_tab_title()` | 534 | Updates tab title |
| `on_tab_changed()` | 612 | Handles tab switch |

#### Prompt Functions

| Function | Line | Purpose |
|----------|------|---------|
| `show_text_prompt()` | 753 | Displays inline text input prompt |
| `show_choice_prompt()` | 767 | Displays inline choice prompt |
| `_on_prompt_ok()` | 851 | Handles prompt OK button |
| `_on_prompt_cancel()` | 864 | Handles prompt Cancel button |
| `_highlight_then_fade()` | 782 | Highlights widget with fade animation |

#### Utility Functions

| Function | Line | Purpose |
|----------|------|---------|
| `append_log()` | 872 | Appends message to log view |
| `on_toggle_log()` | 877 | Shows/hides log view |
| `set_processing()` | 1140 | Enables/disables UI during processing |
| `_refresh_nav()` | 253 | Updates browser navigation buttons |
| `_switch_tab()` | 1153 | Switches to next/previous browser tab |
| `eventFilter()` | 1219 | Global event filter for mouse buttons |

#### Main Entry Point

| Function | Line | Purpose |
|----------|------|---------|
| `run_gui()` | 1268 | Initializes and runs PyQt6 application |

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

### To modify GUI layout or behavior:
- **File**: `gui.py`
- **Main window**: `MainWindow.__init__()` (line 268)
- **Single tab**: Lines 299-338
- **Bulk tab**: Lines 341-358
- **Browser panel**: Lines 389-424

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
├── gui.py                   # GUI application (1306 lines)
├── amazon.py                # Amazon scraping (247 lines)
├── ebay.py                  # eBay listing (344 lines)
├── tokens.py                # OAuth management (210 lines)
├── CentralFunctions.py      # Utilities (395 lines)
├── bulk_parser.py           # Bulk parsing (87 lines)
├── ui_bridge.py             # UI abstraction (26 lines)
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
