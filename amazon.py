# amazon.py
from __future__ import annotations
import requests
import json
import re
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

# Preferred ID order to try for product info tables
_ID_ORDER = ['prodDetails', 'tech']


def handle_table(page, id):
    parent = page.find(id=id)
    if not parent:
        return {}
    prod_info = parent.find_all('tr')
    prod_info_dict = {}
    for info in prod_info:
        th = info.find('th')
        td = info.find('td')
        if not th or not td:
            continue
        key = th.text.strip()
        if key.lower() not in IGNORED_KEYS:
            value = td.text.strip().encode("ascii", "ignore").decode()
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

# New: parse product facts expander section
# Example XPath: //*[@id="productFactsDesktopExpander"]/div[1]/div
# Amazon markup typically contains multiple div.product-facts-detail entries with left/right columns.

def get_product_facts(page, id='productFactsDesktopExpander') -> Dict[str, str]:
    facts: Dict[str, str] = {}
    try:
        root = page.find(id=id)
        if not root:
            return facts
        # Each detail row is typically a div with class 'product-facts-detail'
        for row in root.find_all('div', class_='product-facts-detail'):
            try:
                left = row.find('div', class_='a-col-left') or row.select_one('.a-col-left')
                right = row.find('div', class_='a-col-right') or row.select_one('.a-col-right')
                # Labels and values are generally nested spans; use get_text to be robust
                key = left.get_text(separator=' ', strip=True) if left else ''
                value = right.get_text(separator=' ', strip=True) if right else ''
                key = (key or '').strip()
                value = (value or '').strip()
                if not key or not value:
                    continue
                # Clean up: remove non-word punctuation except spaces and basic separators
                key_clean = re.sub(r'[^\w\s-]', '', key).strip()
                # Normalise whitespace in value
                value_clean = re.sub(r'\s+', ' ', value)
                if key_clean and key_clean.lower() not in IGNORED_KEYS:
                    facts[key_clean] = value_clean.encode("ascii", "ignore").decode()
            except Exception:
                continue
        return facts
    except Exception:
        return facts

# New: parse product facts UL list under the expander section
# XPath: //*[@id="productFactsDesktopExpander"]/div[1]/ul

def get_product_facts_list(page, id='productFactsDesktopExpander') -> list[str]:
    items: list[str] = []
    try:
        root = page.find(id=id)
        if not root:
            return items
        # Target the first child div then ul within it, or any ul fallback
        first_div = None
        for child in root.find_all(recursive=False):
            if child.name == 'div':
                first_div = child
                break
        ul = None
        if first_div:
            ul = first_div.find('ul')
        if not ul:
            # Fallback: any UL directly under root
            ul = root.find('ul')
        if not ul:
            return items
        for li in ul.find_all('li'):
            span = li.find('span')
            text = span.get_text(separator=' ', strip=True) if span else li.get_text(separator=' ', strip=True)
            text = (text or '').strip()
            if text:
                text = re.sub(r"\s+", " ", text)
                items.append(text)
        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for t in items:
            if t not in seen:
                deduped.append(t)
                seen.add(t)
        return deduped
    except Exception:
        return items

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
        urls = []
        for img in initial_images:
            if not isinstance(img, dict):
                continue
            hi_res = img.get('hiRes')
            if isinstance(hi_res, str) and hi_res.strip():
                urls.append(hi_res.strip())
        return urls
    except json.JSONDecodeError as e:
        print(f"JSON decoding error: {e}")
        return []


def get_info(page, ids=None):
    # Avoid mutable default; use module order if none provided
    id_order = list(ids) if ids is not None else list(_ID_ORDER)
    for id in id_order:
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


def get_whats_in_the_box(page) -> list[str]:
    """Extract texts under the Amazon 'What's in the box' list.
    XPath equivalent: //*[@id="witb-content-list"]/li/span
    Returns a list of strings (cleaned), or empty list if none found.
    """
    try:
        container = page.find(id='witb-content-list')
        if not container:
            return []
        items = []
        for li in container.find_all('li'):
            # Prefer span within li; fallback to li text
            span = li.find('span')
            text = span.get_text(separator=' ', strip=True) if span else li.get_text(separator=' ', strip=True)
            text = (text or '').strip()
            if text:
                # Normalise whitespace
                text = re.sub(r"\s+", " ", text)
                items.append(text)
        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for t in items:
            if t not in seen:
                deduped.append(t)
                seen.add(t)
        return deduped
    except Exception:
        return []

# Public API

def scrape_amazon(url: str, note: str = "", quantity: Optional[int] = None, custom_specifics: Optional[Dict[str, str]] = None, io: Optional[IOBridge] = None) -> Dict[str, Any]:
    """Scrape an Amazon product page and return a product dict."""
    io = io or IOBridge()
    custom_specifics = custom_specifics or {}

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
    prod_info_dict['prodDetails'] = get_info(page, _ID_ORDER)

    # Include Product facts under a unified 'Product details' heading if available
    product_facts = get_product_facts(page)
    product_facts_list = get_product_facts_list(page)
    try:
        if product_facts or product_facts_list:
            merged_details = dict(prod_info_dict.get('prodDetails', {}))
            merged_details.update(product_facts)
            if product_facts_list:
                # Store as a single string inside Product details to satisfy typing of detail dict
                merged_details['FactsList'] = '; '.join(product_facts_list)
            prod_info_dict['Product details'] = merged_details
        elif prod_info_dict.get('prodDetails'):
            prod_info_dict['Product details'] = dict(prod_info_dict['prodDetails'])
    except Exception:
        if product_facts or product_facts_list:
            fallback = dict(product_facts)
            if product_facts_list:
                fallback['FactsList'] = '; '.join(product_facts_list)
            prod_info_dict['Product details'] = fallback

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

    # New: What's in the box
    prod_info_dict['whatIsInTheBox'] = get_whats_in_the_box(page)

    prod_info_dict['importantInformation'] = handle_html_content(page, 'important-information')

    title_element = page.find(id='productTitle')
    raw_title = getattr(title_element, 'text', '') if title_element else ""
    title_text = raw_title.strip() if raw_title else ""
    if title_text:
        prod_info_dict['Title'] = title_text.encode("ascii", "ignore").decode()
    else:
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

    # Attempt to generate item specifics using Gemini AI (if available)
    try:
        from gemini_helper import suggest_item_specifics_with_gemini

        try:
            generated = suggest_item_specifics_with_gemini(prod_info_dict, io=io)
            if isinstance(generated, dict) and generated:
                prod_info_dict['generatedSpecifics'] = generated
        except Exception as exc:
            io.log(f"Gemini generation error: {exc}")
    except Exception as e:
        # gemini_helper not present or failed to import; skip gracefully
        print(f"Gemini generation error: {e}")
        pass

    io.log("Amazon scrape complete")
    return prod_info_dict
