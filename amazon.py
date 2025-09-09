# amazon.py
import requests
import json
import re
import ast
import argparse  # NEW
from bs4 import BeautifulSoup

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="", help="Amazon product URL")
    ap.add_argument("--out", default="./product.json", help="Output JSON path")
    ap.add_argument("--custom-specifics", default="{}", help="JSON string of custom specifics dict")
    ap.add_argument("--note", default="", help="Seller note to carry over")
    ap.add_argument("--quantity", default="", help="Quantity to carry over")
    return ap.parse_args()

args = parse_args()
url = args.url.strip() or str(input("Enter Amazon URL: "))

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:66.0) Gecko/20100101 Firefox/66.0",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "DNT": "1",
    "Connection": "close",
    "Upgrade-Insecure-Requests": "1"
}

print("Sending Page Request")
page_request = requests.get(url, headers=headers)
print("Parsing page data")
page_content = page_request.text
page = BeautifulSoup(page_content, "html.parser")
print("Page data parsed")

IGNORED_KEYS = {k.lower() for k in {'ASIN','Customer Reviews','Best Sellers Rank','Date First Available'}}

with open("website.html", "w", encoding="utf-8") as f:
    f.write(page_content)

def handle_table(id):
    prod_info = (page.find(id=id).find_all('tr'))
    prod_info_dict = {}
    for info in prod_info:
        key = info.find('th').text.strip()
        if key.lower() not in IGNORED_KEYS:
            value = info.find('td').text.strip().encode("ascii", "ignore").decode()
            prod_info_dict[key] = value
    return prod_info_dict

def handle_alt_table(id):
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

def handle_list(id):
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

def handle_html_content(id):
    element = page.find(id=id)
    return str(element) if element else None

def get_image_urls(soup):
    script_tag = soup.find('script', string=re.compile(r'P\.when\(\'A\'\)\.register\("ImageBlockATF"'))
    if not script_tag or not script_tag.string:
        return []
    script_content = script_tag.string
    match = re.search(r"var data = (\{.*\});", script_content, re.DOTALL)
    if not match:
        return []
    js_object_str = match.group(1)
    py_literal_str = js_object_str.replace('null', 'None').replace('false', 'False').replace('true', 'True')
    py_literal_str = re.sub(r'Date\.now\(\)', 'None', py_literal_str)
    try:
        data_obj = ast.literal_eval(py_literal_str)
        initial_images = data_obj.get('colorImages', {}).get('initial', [])
        hi_res_urls = [img['hiRes'] for img in initial_images if isinstance(img, dict) and img.get('hiRes')]
        ordered_unique_urls = []
        for u in hi_res_urls:
            if u not in ordered_unique_urls:
                ordered_unique_urls.append(u)
        return ordered_unique_urls
    except (ValueError, SyntaxError, KeyError):
        return []

ids = ['prodDetails', 'tech']

def get_info(ids=ids):
    for id in ids:
        try:
            match id:
                case 'prodDetails':
                    return handle_table(id)
                case 'tech':
                    return handle_alt_table(id)
        except AttributeError:
            continue
    return {}

def get_product_overview(id='productOverview_feature_div'):
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

# --- SCRIPT EXECUTION ---
prod_info_dict = {}
prod_info_dict['URL'] = url
prod_info_dict['prodDetails'] = get_info(ids)

try:
    featuredBullets_list = page.find(id='feature-bullets')
    bullet_points = featuredBullets_list.find_all('li')
    featuredBullets_array = [
        point.find('span', class_='a-list-item').get_text(strip=True)
        for point in bullet_points if point.find('span', class_='a-list-item')
    ]
    prod_info_dict['featuredBullets'] = featuredBullets_array
except AttributeError:
    prod_info_dict['featuredBullets'] = []

prod_info_dict['importantInformation'] = handle_html_content('important-information')

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

prod_info_dict['productOverview'] = get_product_overview()
details = handle_list('detailBullets_feature_div')
if details:
    prod_info_dict['detailBullets'] = details
prod_info_dict['imageUrls'] = get_image_urls(page)

# Carry-through values from bulk parser (if provided)
try:
    custom_specifics = json.loads(args.custom_specifics)
    if isinstance(custom_specifics, dict):
        prod_info_dict['customSpecifics'] = custom_specifics
except json.JSONDecodeError:
    pass

if args.note:
    prod_info_dict['sellerNote'] = args.note

if args.quantity:
    try:
        prod_info_dict['quantity'] = int(args.quantity)
    except ValueError:
        pass

# Write JSON
with open(args.out, "w", encoding="utf-8") as outfile:
    json.dump(prod_info_dict, outfile, indent=4)

print("\nFinished writing to", args.out)
print(json.dumps(prod_info_dict, indent=2))
