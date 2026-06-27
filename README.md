# Amazon-To-eBay Bot

Automates scraping Amazon UK product listings and creating eBay listings via a browser-based UI.

## Features

- 🔍 Scrapes product details, images, and descriptions from Amazon UK
- 📦 Creates eBay listings with automatic category mapping and item specifics
- 📊 Bulk processing with pause/resume support
- 💰 Automatic pricing with eBay fee calculations
- 🔐 OAuth 2.0 authentication with eBay APIs

## Prerequisites

- Python 3.10+
- eBay Developer Account with API credentials

## Installation

```bash
git clone https://github.com/Adam-Developing/Amazon-To-Ebay-Bot.git
cd Amazon-To-Ebay-Bot
pip install -r requirements.txt
```

## eBay Developer Setup

1. Register at [developer.ebay.com](https://developer.ebay.com/)
2. Create a Production Keyset and note your **App ID**, **Cert ID**, and **Dev ID**
3. Add a RuName with redirect URL: `http://localhost:5000/callback`
4. Enable the required OAuth scopes: `sell.inventory`, `sell.marketing`, `sell.account`, `sell.fulfillment`

## Configuration

Edit the `.env` file in the project root:

```bash
EBAY_CLIENT_ID=YourAppID
EBAY_CLIENT_SECRET=YourCertID
EBAY_DEV_ID=YourDevID
EBAY_RUNAME=YourRuName
EBAY_REDIRECT_URI_HOST=http://localhost:5000/callback
SELLER_PAY_FEE=True
EBAY_FIXED_FEE=0.72
```

## Usage

Start the app:
```bash
python main.py
```
Then open `http://localhost:5000` in your browser.

**First run:** Click **"Authorize eBay / Refresh Tokens"** and log in with your eBay seller account.

### Single Item
1. Paste an Amazon UK URL and optionally set quantity, note, and custom specifics
2. Click **"Scrape Amazon"**, then **"List on eBay"**

### Bulk Listing
Switch to the **Bulk** tab and paste items in this format:
```
https://www.amazon.co.uk/dp/B08N5WRWNW
Quantity: 2
Note: Gift item
Size: Large | Colour: Blue

https://www.amazon.co.uk/dp/B07XYZ1234
```

## Troubleshooting

| Issue | Fix |
|---|---|
| Token errors | Re-authorize via the button in the UI |
| Price/title shows N/A | Enter manually when prompted; check the Amazon URL is valid |
| Auth redirect fails | Ensure `EBAY_REDIRECT_URI_HOST` matches your RuName redirect URL |
| Missing modules | Re-run `pip install -r requirements.txt` |

## Disclaimer

Use in accordance with Amazon's and eBay's terms of service. This tool is provided for educational and personal use only.
