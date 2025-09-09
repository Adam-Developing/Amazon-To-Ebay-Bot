import os

import requests
import xml.etree.ElementTree as ET

from dotenv import load_dotenv

load_dotenv()
# ---- eBay aspect key mapping (edit here) ------------------------------------
# Left side: various inputs you might see (Amazon, bulk, user paste)
# Right side: the final eBay aspect name to send.
# --- Mapping: edit on the left; exact eBay aspect name on the right (case-sensitive) ---
EBAY_ASPECT_KEY_MAP = {
    "size name": "Size",
    "size": "Size",
    "style name": "Style",
    "style": "Style",
    "colour name": "Colour",
    "color name": "Colour",
    "colour": "Colour",
    "color": "Colour",
    "pattern": "Pattern",
    "material": "Material",
    "brand": "Brand",
    "model": "Model",
    "type": "Type",
    "variant": "Variant",
    "edition": "Edition",
    "ram": "RAM",
    "storage": "Storage Capacity",
    "capacity": "Capacity",
    "platform": "Platform",
    "connectivity": "Connectivity",
    "power": "Power",
    "wattage": "Wattage",
    "voltage": "Voltage",
    "length": "Length",
    "width": "Width",
    "height": "Height",
    "flavour": "Flavour",
    "flavor": "Flavour",
    "pack size": "Pack Size",
    "quantity per pack": "Quantity per Pack",
    "band size": "Band Size",
    "cup size": "Cup Size",
}

def _norm(s: str) -> str:
    import re
    s = (s or "").strip().lower()
    s = re.sub(r'[\u2010-\u2015]', '-', s)  # normalise dashes
    s = re.sub(r'[^a-z0-9\s/+.-]', '', s)
    s = re.sub(r'\s+', ' ', s)
    return s

def map_to_ebay_aspect_name(input_key: str) -> str | None:
    """Case-insensitive input, returns the exact-cased eBay aspect name or None."""
    k = _norm(input_key)
    if k in EBAY_ASPECT_KEY_MAP:
        return EBAY_ASPECT_KEY_MAP[k]
    for suffix in (" name", " option", " value"):
        if k.endswith(suffix):
            base = k[: -len(suffix)]
            if base in EBAY_ASPECT_KEY_MAP:
                return EBAY_ASPECT_KEY_MAP[base]
    return None

def map_one_dict(d: dict) -> dict:
    """Map a dict's keys; if no mapping exists, keep the exact original key."""
    out = {}
    for k, v in (d or {}).items():
        mapped = map_to_ebay_aspect_name(str(k))
        out[mapped if mapped else str(k)] = str(v)
    return out

def merge_specifics_in_order(*dicts: dict) -> dict:
    """
    Merge multiple specifics dicts in order; later dicts override earlier ones.
    Keys are compared case-sensitively (because eBay aspect names are case-sensitive).
    """
    merged = {}
    for d in dicts:
        for k, v in (d or {}).items():
            if v is None:
                continue
            merged[str(k)] = str(v)
    return merged

def categoryTreeID(access_token):
    """
    Fetches the default category tree ID from the eBay API for the GB marketplace.
    """
    headers = {
        'Authorization': 'Bearer ' + access_token,
    }

    params = {
        'marketplace_id': 'EBAY_GB',
    }

    try:
        response = requests.get(
            'https://api.ebay.com/commerce/taxonomy/v1/get_default_category_tree_id',
            params=params,
            headers=headers
        )

        response.raise_for_status()

        categoryJson = response.json()
        categoryTreeId = categoryJson["categoryTreeId"]

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        categoryTreeId = 3

    except Exception as err:
        print(f"An error occurred: {err}")
        categoryTreeId = 3
    return categoryTreeId


def categoryID(access_token, categoryTreeId, title_variable):
    headers = {
        'Authorization': 'Bearer ' + access_token,
    }

    params = {
        'q': title_variable,
    }

    # The category tree ID '3' is part of the URL
    url = f'https://api.ebay.com/commerce/taxonomy/v1/category_tree/{categoryTreeId}/get_category_suggestions'

    try:
        response = requests.get(url, params=params, headers=headers)

        # Raise an exception for bad status codes (4xx or 5xx)
        response.raise_for_status()

        CategoryID = response.json()['categorySuggestions'][0]['category']['categoryId']


    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        CategoryID = 14254

    except Exception as err:
        print(f"An error occurred: {err}")
        CategoryID = 14254
    return CategoryID




def get_item_specifics(token, category_tree_id, category_id, product_data):
    """
    Pipeline:
      1) Collect inputs (bulk customSpecifics, additional paste, scraped data).
      2) Map all keys via EBAY_ASPECT_KEY_MAP; keep exact key when no mapping exists.
      3) Merge in order so user-supplied overrides auto suggestions.
      4) Fetch taxonomy; if a required aspect is missing, prompt.
         - If SELECTION_ONLY and our value not in options -> prompt to choose/confirm.
         - Otherwise keep our value and don't ask.
    """
    headers = {'Authorization': f'Bearer {token}'}
    url = f"https://api.ebay.com/commerce/taxonomy/v1/category_tree/{category_id if str(category_tree_id).isdigit() else category_tree_id}/get_item_aspects_for_category?category_id={category_id}"

    try:
        print("\n--- Populating Item Specifics ---")

        # Inputs from earlier stages
        bulk_custom = product_data.get('customSpecifics', {}) or {}

        # Show what we already have from bulk (for transparency)
        if bulk_custom:
            print("\nExisting custom specifics (raw):")
            for k, v in bulk_custom.items():
                print(f"  - {k}: {v}")

        # Additional pasted specifics (user)
        pasted_string = input(
            "\nPaste additional custom specifics (e.g., Name: Value | Name: Value) or press Enter to continue: "
        ).strip()
        pasted_dict = {}
        if pasted_string:
            for part in pasted_string.split('|'):
                if ':' in part:
                    k, v = part.split(':', 1)
                    k, v = k.strip(), v.strip()
                    if k and v:
                        pasted_dict[k] = v

        # Scraped product data (we treat these as suggestions; your inputs will override)
        prod_details = product_data.get('prodDetails', {}) or {}
        prod_overview = product_data.get('productOverview', {}) or {}

        # Map everything (unmapped keys are kept exact)
        mapped_bulk       = map_one_dict(bulk_custom)
        mapped_paste      = map_one_dict(pasted_dict)
        mapped_details    = map_one_dict(prod_details)
        mapped_overview   = map_one_dict(prod_overview)

        # Merge order defines precedence:
        # 1) scraped suggestions (details/overview)
        # 2) bulk custom (from your parser)
        # 3) additional paste (typed just now)  -> strongest
        pre_merged = merge_specifics_in_order(mapped_details, mapped_overview, mapped_bulk, mapped_paste)

        # Fetch taxonomy
        response = requests.get(
            f"https://api.ebay.com/commerce/taxonomy/v1/category_tree/{category_tree_id}/get_item_aspects_for_category",
            params={"category_id": category_id},
            headers=headers
        )
        response.raise_for_status()
        taxonomy = response.json()

        # Validate against taxonomy: add only where appropriate; prompt if required and missing/invalid
        item_specifics = dict(pre_merged)  # start with your mapped+merged values

        def has_value_for(aspect_name: str) -> bool:
            return aspect_name in item_specifics and str(item_specifics[aspect_name]).strip() != ""

        for aspect in taxonomy.get('aspects', []):
            name = aspect['localizedAspectName']  # exact eBay casing
            mode = aspect.get('aspectConstraint', {}).get('aspectMode')
            required = aspect.get('aspectConstraint', {}).get('aspectRequired', False)
            options = [ov.get('localizedValue') for ov in aspect.get('aspectValues', [])] if aspect.get('aspectValues') else []

            # If we already have a value after mapping+merge:
            if has_value_for(name):
                val = item_specifics[name]
                if mode == 'SELECTION_ONLY' and options:
                    # If our value isn't a valid option, we must ask
                    if not any(val.lower() == (opt or "").lower() for opt in options):
                        print(f"\n'{name}' must be selected from allowed values.")
                        print("Allowed options:")
                        for i, opt in enumerate(options, start=1):
                            print(f"  {i}: {opt}")
                        while True:
                            pick = input(f"Enter number 1-{len(options)} or type exact value: ").strip()
                            try:
                                idx = int(pick)
                                if 1 <= idx <= len(options):
                                    item_specifics[name] = options[idx - 1]
                                    break
                            except ValueError:
                                if any((opt or "").lower() == pick.lower() for opt in options):
                                    item_specifics[name] = pick
                                    break
                            print("Invalid choice. Try again.")
                # else: free text, our value stands (overwrites any suggestion)
                continue

            # We don't have a value yet:
            if required:
                print(f"\n❓ Required aspect '{name}' is missing.")
                if mode == 'SELECTION_ONLY' and options:
                    print("Please select:")
                    for i, opt in enumerate(options, start=1):
                        print(f"  {i}: {opt}")
                    while True:
                        raw = input(f"Enter number 1-{len(options)} or type exact value: ").strip()
                        try:
                            idx = int(raw)
                            if 1 <= idx <= len(options):
                                item_specifics[name] = options[idx - 1]
                                break
                        except ValueError:
                            if any((opt or "").lower() == raw.lower() for opt in options):
                                item_specifics[name] = raw
                                break
                        print("Invalid choice. Try again.")
                else:
                    while True:
                        val = input(f"Please enter a value for '{name}': ").strip()
                        if val:
                            item_specifics[name] = val
                            break
                        print("This field cannot be empty.")

        print("\n--- Finished Populating Item Specifics ---")
        return item_specifics

    except requests.exceptions.HTTPError as e:
        print(f"❌ API Error fetching aspects: {e.response.text}")
        return {}
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        return {}


def set_seller_note(item_id, note, user_token, app_id, dev_id, cert_id):
    """
    Sets a private seller note on an existing eBay item using SetUserNotes.
    """
    print(f"\n--- Adding private note to Item ID: {item_id} ---")

    endpoint = "https://api.ebay.com/ws/api.dll"
    headers = {
        "X-EBAY-API-CALL-NAME": "SetUserNotes",
        "X-EBAY-API-SITEID": "3",
        "X-EBAY-API-APP-NAME": app_id,
        "X-EBAY-API-DEV-NAME": dev_id,
        "X-EBAY-API-CERT-NAME": cert_id,
        "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
        "Content-Type": "text/xml"
    }

    # Escape the note text for XML safety
    escaped_note = note.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
    <SetUserNotesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
      <RequesterCredentials>
        <eBayAuthToken>{user_token}</eBayAuthToken>
      </RequesterCredentials>
      <ItemID>{item_id}</ItemID>
      <Action>AddOrUpdate</Action>
      <NoteText>{escaped_note}</NoteText>
    </SetUserNotesRequest>
    """

    try:
        response = requests.post(endpoint, data=xml_body.encode('utf-8'), headers=headers)
        tree = ET.fromstring(response.content)
        namespace = '{urn:ebay:apis:eBLBaseComponents}'
        ack = tree.find(f'{namespace}Ack').text

        if ack in ['Success', 'Warning']:
            print(f"✅ Successfully added/updated the seller note.")
        else:
            print(f"❌ Failed to add seller note.")
            for error in tree.findall(f'{namespace}Errors'):
                short_message = error.find(f'{namespace}ShortMessage').text
                print(f"   Error: {short_message}")
    except Exception as e:
        print(f"An unexpected error occurred while setting the seller note: {e}")


FIXED_FEE = float(os.getenv("EBAY_FIXED_FEE", 0.72))


def calculate_ebay_fee(item_price):
    """
    Calculates the eBay selling fee using the global FIXED_FEE.

    Args:
        item_price (float): The final selling price of the item.

    Returns:
        float: The total calculated fee.
    """
    if item_price <= 0:
        return FIXED_FEE

    if item_price <= 300:
        variable_fee = item_price * 0.04
    else:
        tier_1_fee = 300 * 0.04
        portion_in_tier_2 = min(item_price, 4000) - 300
        tier_2_fee = portion_in_tier_2 * 0.02
        variable_fee = tier_1_fee + tier_2_fee

    return FIXED_FEE + variable_fee


def find_minimum_price(target_total):
    """
    Finds the minimum item price 'y' such that y + calculate_ebay_fee(y) >= target_total.
    This function uses the global FIXED_FEE.

    Args:
        target_total (float): The desired minimum total sum.

    Returns:
        float: The calculated minimum original item price.
    """
    # The crossover target where the price might exceed £300, dependent on the fixed fee.
    # Calculated from: 300 + fee(300) = 300 + (FIXED_FEE + 300 * 0.04) = 312 + FIXED_FEE
    crossover_target = 312 + FIXED_FEE

    # Get an initial estimate for the price based on the fee tier
    if target_total > crossover_target:
        # Tier 2 equation: y = (x - (FIXED_FEE + 6)) / 1.02
        # The constant part of the tier 2 fee is FIXED_FEE + (300*0.04) - (300*0.02) = FIXED_FEE + 6
        tier_2_base_fee = FIXED_FEE + 6
        initial_estimate = (target_total - tier_2_base_fee) / 1.02
    else:
        # Tier 1 equation: y = (x - FIXED_FEE) / 1.04
        initial_estimate = (target_total - FIXED_FEE) / 1.04

    # Start searching from the price rounded down to the nearest penny
    current_price = int(initial_estimate * 100) / 100.0

    # Iteratively increase the price by one penny until the total is met or exceeded
    while True:
        fee = calculate_ebay_fee(current_price)

        if current_price + fee >= target_total:
            return current_price

        current_price += 0.01

        # Safety break to prevent potential infinite loops
        if current_price > target_total:
            raise RuntimeError("Could not find a suitable price.")

