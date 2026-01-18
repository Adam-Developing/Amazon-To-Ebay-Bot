# amazon.py
from __future__ import annotations
import requests
import json
import re
import ast
from urllib.parse import urlparse
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup
from ui_bridge import IOBridge

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:66.0) Gecko/20100101 Firefox/66.0",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "DNT": "1",
    "Connection": "close",
    "Upgrade-Insecure-Requests": "1"
}

IGNORED_KEYS = {k.lower() for k in {'ASIN','Customer Reviews','Best Sellers Rank','Date First Available'}}


def handle_table(page, id):
    prod_info = (page.find(id=id).find_all('tr'))
    prod_info_dict = {}
    for info in prod_info:
        key = info.find('th').text.strip()
        if key.lower() not in IGNORED_KEYS:
            value = info.find('td').text.strip().encode("ascii", "ignore").decode()
            prod_info_dict[key] = value
    return prod_info_dict


def handle_alt_table(page, id):
    prod_info = (page.find(id=id).find_all('tr'))
    prod_info_dict = {}
    for info in prod_info:
        try:
            key = info.contents[1].text.strip()
            value = info.contents[3].text.strip().encode("ascii", "ignore").decode()
            prod_info_dict[key] = value
        except (AttributeError, IndexError):
            continue
    return prod_info_dict


def handle_list(page, id):
    parent_div = page.find(id=id)
    if not parent_div:
        return {}
    prod_info = parent_div.find_all('ul')
    if not prod_info:
        return {}
    prod_info_list = prod_info[0].find_all('li')
    prod_info_dict = {}
    for info in prod_info_list:
        try:
            raw_key_text = info.span.contents[1].text
            cleaned_text = re.sub(r'[^\w\s:]', '', raw_key_text)
            key = cleaned_text.replace(':', '').strip()
            if key and key.lower() not in IGNORED_KEYS:
                raw_value_text = info.span.contents[3].text
                value = " ".join(raw_value_text.split())
                prod_info_dict[key] = value
        except (AttributeError, IndexError):
            continue
    return prod_info_dict


def handle_html_content(page, id):
    element = page.find(id=id)
    return str(element) if element else None

def get_image_urls(page):
    # 1. Find the specific script tag containing the image data
    # We look for a script tag that contains the string 'ImageBlockATF'
    script_tag = page.find('script', string=re.compile(r'ImageBlockATF'))

    if not script_tag:
        return []

    script_content = script_tag.string
    if not script_content:
        return []

    # 2. Extract the object inside 'var data = { ... };'
    match = re.search(r"var\s+data\s*=\s*({.*?});", script_content, re.DOTALL)
    if not match:
        return []

    js_obj = match.group(1)

    # 3. Clean the string to make it valid JSON
    # Remove JavaScript comments (////// ...)
    js_obj = re.sub(r"(?<!https:)(?<!http:)//.*", "", js_obj)

    # Replace single quotes with double quotes for keys and values
    # Regex handles keys: 'key': -> "key":
    js_obj = re.sub(r"'(.*?)'\s*:", r'"\1":', js_obj)
    # Remaining single quotes for values: 'value' -> "value"
    js_obj = js_obj.replace("'", '"')

    # 4. Handle JS-specific values
    js_obj = re.sub(r"Date\.now\(\)", "null", js_obj)
    js_obj = js_obj.replace("false", "false").replace("true", "true").replace("null", "null")

    # 5. Clean up trailing commas (common in JS, illegal in JSON)
    js_obj = re.sub(r",\s*}", "}", js_obj)
    js_obj = re.sub(r",\s*]", "]", js_obj)

    try:
        data_obj = json.loads(js_obj)
        initial_images = data_obj.get('colorImages', {}).get('initial', [])
        return [img.get('hiRes') for img in initial_images if isinstance(img, dict) and img.get('hiRes')]
    except json.JSONDecodeError as e:
        print(f"JSON decoding error: {e}")
        return []

ids = ['prodDetails', 'tech']


def get_info(page, ids=ids):
    for id in ids:
        try:
            match id:
                case 'prodDetails':
                    return handle_table(page, id)
                case 'tech':
                    return handle_alt_table(page, id)
        except AttributeError:
            continue
    return {}


def get_product_overview(page, id='productOverview_feature_div'):
    overview_dict = {}
    try:
        overview_section = page.find(id=id)
        if overview_section:
            for info in overview_section.find_all('tr'):
                key = info.contents[1].text.strip()
                value = info.contents[3].text.strip().encode("ascii", "ignore").decode()
                overview_dict[key] = value
    except (AttributeError, IndexError):
        pass
    return overview_dict


# Public API

def scrape_amazon(url: str, note: str = "", quantity: Optional[int] = None, custom_specifics: Optional[Dict[str, str]] = None, io: Optional[IOBridge] = None) -> Dict[str, Any]:
    """Scrape an Amazon product page and return a product dict."""
    io = io or IOBridge()
    custom_specifics = custom_specifics or {}

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or "amazon." not in parsed.netloc.lower():
        raise ValueError("URL must be a valid Amazon product link.")

    io.log("Sending Page Request")
    page_request = requests.get(url, headers=headers)
    io.log("Parsing page data")
    page_content = page_request.text
    page = BeautifulSoup(page_content, "html.parser")
    io.log("Page data parsed")

    # Optionally write page for debugging
    try:
        with open("website.html", "w", encoding="utf-8") as f:
            f.write(page_content)
    except Exception:
        pass

    prod_info_dict: Dict[str, Any] = {}
    prod_info_dict['URL'] = url
    prod_info_dict['prodDetails'] = get_info(page, ids)

    try:
        featuredBullets_list = page.find(id='feature-bullets')
        bullet_points = featuredBullets_list.find_all('li') if featuredBullets_list else []
        featuredBullets_array = [
            point.find('span', class_='a-list-item').get_text(strip=True)
            for point in bullet_points if point.find('span', class_='a-list-item')
        ]
        prod_info_dict['featuredBullets'] = featuredBullets_array
    except Exception:
        prod_info_dict['featuredBullets'] = []

    prod_info_dict['importantInformation'] = handle_html_content(page, 'important-information')

    try:
        title = page.find(id='productTitle').text.strip().encode("ascii", "ignore").decode()
        prod_info_dict['Title'] = title
    except AttributeError:
        prod_info_dict['Title'] = "N/A"

    try:
        price_str = None
        price_span = page.select_one('#corePrice_feature_div .a-price')
        if price_span:
            price_offscreen = price_span.find('span', class_='a-offscreen')
            if price_offscreen:
                price_str = price_offscreen.text.strip()
            else:
                whole_span = price_span.find('span', class_='a-price-whole')
                fraction_span = price_span.find('span', class_='a-price-fraction')
                if whole_span and fraction_span:
                    price_str = f"{whole_span.text.strip()}{fraction_span.text.strip()}"
        if price_str:
            cleaned_price_str = re.sub(r'[^\d.]', '', price_str)
            try:
                prod_info_dict['Price'] = float(cleaned_price_str)
            except (ValueError, TypeError):
                prod_info_dict['Price'] = "N/A"
        else:
            prod_info_dict['Price'] = -1.0
    except Exception:
        prod_info_dict['Price'] = -1.0

    try:
        deal_badge_element = page.find(class_="dealBadge")
        prod_info_dict['tempDeal'] = bool(deal_badge_element)
    except Exception:
        prod_info_dict['tempDeal'] = False

    try:
        coupon_element = page.find(class_="couponLabelText")
        if coupon_element:
            voucher_text = coupon_element.get_text(strip=True)
            cleaned_text = re.sub(r'apply|voucher|terms|shop|items|\|', '', voucher_text, flags=re.IGNORECASE).strip()
            if '%' in cleaned_text:
                value_str = cleaned_text.replace('%', '').strip()
                if value_str:
                    prod_info_dict['discount_type'] = 'percentage'
                    prod_info_dict['discount_value'] = float(value_str) / 100.0
            elif '£' in cleaned_text:
                value_str = cleaned_text.replace('£', '').strip()
                if value_str:
                    prod_info_dict['discount_type'] = 'fixed'
                    prod_info_dict['discount_value'] = float(value_str)
    except Exception:
        pass

    prod_info_dict['productOverview'] = get_product_overview(page)
    details = handle_list(page, 'detailBullets_feature_div')
    if details:
        prod_info_dict['detailBullets'] = details
    prod_info_dict['imageUrls'] = get_image_urls(page)

    # Carry-through values from bulk parser (if provided)
    if isinstance(custom_specifics, dict) and custom_specifics:
        try:
            # Ensure JSON serializable strings
            prod_info_dict['customSpecifics'] = {str(k): str(v) for k, v in custom_specifics.items()}
        except Exception:
            pass

    if note:
        prod_info_dict['sellerNote'] = note

    if quantity is not None:
        try:
            prod_info_dict['quantity'] = int(quantity)
        except Exception:
            pass

    io.log("Amazon scrape complete")
    return prod_info_dict
