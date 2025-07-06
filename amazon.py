# libraries
import requests
import json
import re
import ast
from bs4 import BeautifulSoup

# Get user URL
url = str(input("Enter Amazon URL: "))

# Headers sent with request to not trigger CAPTCHA
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:66.0) Gecko/20100101 Firefox/66.0",
           "Accept-Encoding": "gzip, deflate",
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "DNT": "1",
           "Connection": "close", "Upgrade-Insecure-Requests": "1"}

# Scraping HTML
print("Sending Page Request")
page_request = requests.get(url, headers=headers)
print("Parsing page data")
page_content = page_request.text
page = BeautifulSoup(page_content, "html.parser")
print("Page data parsed")


### * * FUNCTIONS HANDLING DIFFERENT IDS * * ###

# *function handles table type of listing; th is the heading for the product info and td is the value.
def handle_table(id):
    prod_info = (page.find(id=id).find_all('tr'))
    prod_info_dict = {}
    for info in prod_info:
        key = info.find('th').text.strip()
        value = info.find('td').text.strip().encode("ascii", "ignore").decode()
        prod_info_dict[key] = value
    return prod_info_dict


# *function handles the alternate table-listing where only td tags are used and no th tags are used
def handle_alt_table(id):
    prod_info = (page.find(id=id).find_all('tr'))
    prod_info_dict = {}
    # because both tags are the same (td), use .contents to have a list of the child tags.
    for info in prod_info:
        try:
            key = info.contents[1].text.strip()
            value = info.contents[3].text.strip().encode("ascii", "ignore").decode()
            prod_info_dict[key] = value
        except (AttributeError, IndexError):
            continue  # Skip row if format is unexpected
    return prod_info_dict


# * function handles list type listing (<ul>)
def handle_list(id):
    # the DIV wrapping the list can have slightly different names so I find any div matching the ID and then take the first unordered list
    prod_info = page.find(id=id).find_all('ul')[0].find_all('li')
    prod_info_dict = {}
    for info in prod_info:
        try:
            key = info.span.contents[1].text.encode("ascii", "ignore").decode().strip()
            value = info.span.contents[3].text.strip().encode("ascii", "ignore").decode()
            prod_info_dict[key] = value
        except (AttributeError, IndexError):
            continue  # Skip row if format is unexpected
    return prod_info_dict


# * function to extract hi-res image URLs from the page's JavaScript
def get_image_urls(soup):
    """
    Extracts the 'ImageBlockATF' JavaScript block, then parses the JSON-like
    'data' object to get high-resolution image URLs.
    """
    # Step 1: Find the script tag containing the image data.
    script_tag = soup.find('script', string=re.compile(r'P\.when\(\'A\'\)\.register\("ImageBlockATF"'))

    if not script_tag or not script_tag.string:
        print("Could not find the 'ImageBlockATF' script tag.")
        return []

    script_content = script_tag.string

    # Step 2: Extract the entire 'data' object string from the script.
    # This is more robust as it captures the complete object.
    match = re.search(r"var data = (\{.*\});", script_content, re.DOTALL)

    if not match:
        print("Could not find 'var data =' object in the script.")
        return []

    js_object_str = match.group(1)

    # Step 3: Convert the JavaScript object literal string to a Python-parsable string.
    py_literal_str = js_object_str.replace('null', 'None').replace('false', 'False').replace('true', 'True')
    # Replace the JavaScript 'Date.now()' function call with Python's 'None'.
    py_literal_str = re.sub(r'Date\.now\(\)', 'None', py_literal_str)

    try:
        # Use ast.literal_eval for safe evaluation of the string into a Python dict.
        data_obj = ast.literal_eval(py_literal_str)

        # Now that we have the full data object, navigate to the image URLs.
        initial_images = data_obj.get('colorImages', {}).get('initial', [])
        hi_res_urls = [img['hiRes'] for img in initial_images if
                       isinstance(img, dict) and 'hiRes' in img and img['hiRes']]

        # Preserve order while getting unique URLs
        ordered_unique_urls = []
        for url in hi_res_urls:
            if url not in ordered_unique_urls:
                ordered_unique_urls.append(url)

        return ordered_unique_urls

    except (ValueError, SyntaxError, KeyError) as e:
        print(f"Failed to parse image data using ast.literal_eval: {e}")
        print("The extracted data block may be malformed.")
        return []


# List of possible ID values containing product info
ids = ['prodDetails', 'tech', 'detailBullets_feature_div']


# scrape product information into a dictionary
def get_info(ids=ids):
    for id in ids:
        print(f"checking {id} ID")
        try:
            match id:
                case 'prodDetails':
                    return handle_table(id)
                case 'tech':
                    return handle_alt_table(id)
                case 'detailBullets_feature_div':
                    return handle_list(id)
        except AttributeError:
            print(f"ID {id} not found or format is incorrect.")
            continue
    return {}  # Return empty dict if no IDs worked


# gets product overview if available
def get_product_overview(id='productOverview_feature_div'):
    overview_dict = {}
    try:
        overview_section = page.find(id=id)
        if overview_section:
            overview_rows = overview_section.find_all('tr')
            for info in overview_rows:
                # same implementation as the alt_table function
                key = info.contents[1].text.strip()
                value = info.contents[3].text.strip().encode("ascii", "ignore").decode()
                overview_dict[key] = value
    except (AttributeError, IndexError):
        print("Could not parse product overview or it does not exist.")
    return overview_dict


# --- SCRIPT EXECUTION ---

# Initialise main dictionary
prod_info_dict = {}

# Get primary product information and add it as a sub-dictionary
prod_details_data = get_info(ids)
prod_info_dict['prodDetails'] = prod_details_data

# Get item featured bullets as a list of bullet points
try:
    # Find the unordered list with the id 'feature-bullets'
    featuredBullets = page.find(id='feature-bullets')
    # Find all list items (li) within that list
    bullet_points = featuredBullets.find_all('li')
    # Extract the text from each list item's span and store it in a list
    featuredBullets_array = [point.find('span', class_='a-list-item').get_text(strip=True) for point in bullet_points if
                         point.find('span', class_='a-list-item')]
    prod_info_dict['featuredBullets'] = featuredBullets_array
except AttributeError:
    prod_info_dict['featuredBullets'] = []  # Return an empty list if not found

# Get item title
try:
    title = page.find(id='productTitle').text.strip().encode("ascii", "ignore").decode()
    prod_info_dict['Title'] = title
except AttributeError:
    prod_info_dict['Title'] = "Not Found"

# Get item price
try:
    price_span = page.select_one('#corePrice_feature_div .a-price')
    if price_span:
        price_offscreen = price_span.find('span', class_='a-offscreen')
        if price_offscreen:
            prod_info_dict['Price'] = price_offscreen.text.strip()
        else:
            # Fallback for when the main price is not in an offscreen span
            # symbol = price_span.find('span', class_='a-price-symbol').text.strip()
            whole = price_span.find('span', class_='a-price-whole').text.strip()
            fraction = price_span.find('span', class_='a-price-fraction').text.strip()
            prod_info_dict['Price'] = f"{whole}{fraction}"
    else:
        prod_info_dict['Price'] = "Not Found"

except AttributeError:
    prod_info_dict['Price'] = "Not Found"

# Get product overview and add it as a sub-dictionary
product_overview = get_product_overview()
prod_info_dict['productOverview'] = product_overview

# Get hi-res image URLs and add them to the dictionary
prod_info_dict['imageUrls'] = get_image_urls(page)

# Serializing JSON
json_object = json.dumps(prod_info_dict, indent=4)

# Writing to JSON
with open("./product.json", "w") as outfile:
    outfile.write(json_object)

print("\nFinished writing to product.json")
print(json_object)
