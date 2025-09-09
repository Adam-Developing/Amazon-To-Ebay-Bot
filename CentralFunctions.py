import os

import requests
import xml.etree.ElementTree as ET

from dotenv import load_dotenv

load_dotenv()
# ---- eBay aspect key mapping (edit here) ------------------------------------
# Left side: various inputs you might see (Amazon, bulk, user paste)
# Right side: the final eBay aspect name to send.
EBAY_ASPECT_KEY_MAP = {
    # Core apparel / variants
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

    # Footwear / apparel details
    "shoe size": "Shoe Size",
    "waist": "Waist Size",
    "chest": "Chest Size",
    "fit": "Fit",
    "age range": "Age Range",
    "gender": "Department",            # sometimes eBay expects 'Department'/'Men/Women/Unisex'

    # Electronics / general specs
    "capacity": "Capacity",
    "storage": "Storage Capacity",
    "ram": "RAM",
    "connectivity": "Connectivity",
    "platform": "Platform",
    "power": "Power",
    "wattage": "Wattage",
    "voltage": "Voltage",

    # Dimensions
    "length": "Length",
    "width": "Width",
    "height": "Height",
    "dimensions": "Dimensions",

    # Health/beauty/supplements
    "flavour": "Flavour",
    "flavor": "Flavour",
    "pack size": "Pack Size",
    "quantity per pack": "Quantity per Pack",

    # Lingerie / bras
    "band size": "Band Size",
    "cup size": "Cup Size",

    # Fallback examples (add to taste)
    "style group": "Style",
    "size option": "Size",
    "colour option": "Colour",
}

# -----------------------------------------------------------------------------

def _norm(s: str) -> str:
    """Normalise keys for matching: lowercase, collapse spaces, strip punctuation-like chars."""
    import re
    s = (s or "").strip().lower()
    s = re.sub(r'[\u2010-\u2015]', '-', s)  # normalise weird dashes
    s = re.sub(r'[^a-z0-9\s/+-]', '', s)    # keep alnum, spaces, / + -
    s = re.sub(r'\s+', ' ', s)
    return s

def map_to_ebay_aspect_name(input_key: str) -> str | None:
    """
    Returns the mapped eBay aspect name for an input key, or None if no mapping exists.
    """
    k = _norm(input_key)
    # Direct match
    if k in EBAY_ASPECT_KEY_MAP:
        return EBAY_ASPECT_KEY_MAP[k]
    # Gentle heuristics: strip trailing words like 'name'
    # e.g. "size name" -> "size", "colour option" -> "colour"
    for suffix in (" name", " option", " value"):
        if k.endswith(suffix):
            base = k[: -len(suffix)]
            if base in EBAY_ASPECT_KEY_MAP:
                return EBAY_ASPECT_KEY_MAP[base]
    return None

def map_specifics_dict(d: dict) -> tuple[dict, dict]:
    """
    Map an input specifics dict to eBay aspect names using EBAY_ASPECT_KEY_MAP.
    Returns (mapped, unmapped). If a key maps to the same eBay name multiple times,
    later values override earlier ones.
    """
    mapped: dict = {}
    unmapped: dict = {}
    for k, v in (d or {}).items():
        tgt = map_to_ebay_aspect_name(str(k))
        if tgt:
            mapped[tgt] = v
        else:
            unmapped[k] = v
    return mapped, unmapped


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
    Gets required and custom aspects for a category. It:
      1) Shows & pre-loads custom specifics parsed from bulk input (product_data['customSpecifics']), mapping them to eBay aspect names.
      2) Lets you paste additional specifics; maps them to eBay names.
      3) Auto-fills from product.json (prodDetails/productOverview); also tries to map common Amazon-ish keys to the current eBay aspect.
      4) Prompts for any remaining *required* aspects (selection-only or free text).
    """
    headers = {'Authorization': f'Bearer {token}'}
    url = f"https://api.ebay.com/commerce/taxonomy/v1/category_tree/{category_tree_id}/get_item_aspects_for_category?category_id={category_id}"

    item_specifics: dict[str, str] = {}

    try:
        print("\n--- Populating Item Specifics ---")

        # --- 0) Bulk/custom specifics from product_data (already parsed earlier) ---
        bulk_custom = product_data.get('customSpecifics', {})
        if isinstance(bulk_custom, dict) and bulk_custom:
            mapped_bulk, unmapped_bulk = map_specifics_dict(bulk_custom)
            if mapped_bulk:
                print("\nExisting custom specifics (mapped to eBay names):")
                for k, v in mapped_bulk.items():
                    print(f"  - {k}: {v}")
                item_specifics.update({str(k): str(v) for k, v in mapped_bulk.items()})
            if unmapped_bulk:
                print("\n(Info) Unmapped custom specifics (kept as-is unless a required aspect matches):")
                for k, v in unmapped_bulk.items():
                    print(f"  - {k}: {v}")
                # We keep them aside; may still use if they correspond to a required aspect name directly
                # (Handled below during the per-aspect loop)

        # --- 1) Additional pasted specifics (optional) ---
        pasted_string = input(
            "\nPaste additional custom specifics (e.g., Name: Value | Name: Value) or press Enter to continue: "
        ).strip()

        if pasted_string:
            pairs = pasted_string.split('|')
            temp_dict = {}
            for pair in pairs:
                if ':' in pair:
                    key, value = pair.split(':', 1)
                    clean_key = key.strip()
                    clean_value = value.strip()
                    if clean_key and clean_value:
                        temp_dict[clean_key] = clean_value

            mapped_paste, unmapped_paste = map_specifics_dict(temp_dict)
            if mapped_paste:
                print("✅ Added (mapped) custom specifics:")
                for k, v in mapped_paste.items():
                    print(f"  - {k}: {v}")
                item_specifics.update(mapped_paste)
            if unmapped_paste:
                print("(Info) Additional unmapped specifics captured (kept for later matching):")
                for k, v in unmapped_paste.items():
                    print(f"  - {k}: {v}")
                # We'll try to match them to current aspect names during the aspect loop
        else:
            unmapped_paste = {}

        # --- 2) Fetch and process API-defined aspects ---
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Prepare product data for auto-fill
        prod_details = product_data.get('prodDetails', {}) or {}
        prod_overview = product_data.get('productOverview', {}) or {}

        # Normalised views to help match later
        prod_details_norm = { _norm(k): v for k, v in prod_details.items() }
        prod_overview_norm = { _norm(k): v for k, v in prod_overview.items() }

        # Helper: try find a value in scraped dicts via explicit mapping
        def try_mapped_autofill(target_aspect_name: str) -> str | None:
            """
            For a given eBay aspect name, look in prod_details/prod_overview for keys which map to that name.
            """
            wanted = target_aspect_name.strip()
            for src_dict in (prod_details, prod_overview):
                for k, v in src_dict.items():
                    mapped = map_to_ebay_aspect_name(k)
                    if mapped and mapped.lower() == wanted.lower():
                        return v
            return None

        # Also hold any unmapped custom specifics from earlier steps
        # Combine for later: prefer paste over bulk if same key appears
        combined_unmapped = {}
        # add bulk first then paste to let paste override
        if isinstance(bulk_custom, dict):
            for k, v in bulk_custom.items():
                if not map_to_ebay_aspect_name(k):
                    combined_unmapped[k] = v
        if isinstance(locals().get('unmapped_paste', {}), dict):
            for k, v in unmapped_paste.items():
                if not map_to_ebay_aspect_name(k):
                    combined_unmapped[k] = v

        for aspect in data.get('aspects', []):
            name = aspect['localizedAspectName']
            is_required = aspect.get('aspectConstraint', {}).get('aspectRequired', False)

            # If already provided (from mapped bulk/paste), skip
            if name in item_specifics:
                print(f"Using provided value for '{name}': {item_specifics[name]}")
                continue

            # 2a. Direct match from product_data if keys already match eBay aspect name
            # (case-insensitive)
            found_value = None
            if _norm(name) in prod_details_norm:
                found_value = prod_details_norm[_norm(name)]
            elif _norm(name) in prod_overview_norm:
                found_value = prod_overview_norm[_norm(name)]

            # 2b. If not, try mapped auto-fill (Amazon-ish keys -> eBay aspect)
            if not found_value:
                found_value = try_mapped_autofill(name)

            # 2c. If still not found, see if any UNMAPPED custom key literally matches the eBay aspect name
            if not found_value:
                for k, v in list(combined_unmapped.items()):
                    if _norm(k) == _norm(name):
                        found_value = v
                        break

            if found_value:
                item_specifics[name] = found_value
                print(f"Found '{name}' automatically: {found_value}")
                continue

            # 2d. Prompt if required
            if is_required:
                print(f"\n❓ Required aspect '{name}' not found automatically.")
                mode = aspect.get('aspectConstraint', {}).get('aspectMode')

                if mode == 'SELECTION_ONLY' and aspect.get('aspectValues'):
                    options = aspect['aspectValues']
                    print(f"Please select one for '{name}':")
                    for i, option in enumerate(options, start=1):
                        print(f"  {i}: {option['localizedValue']}")
                    while True:
                        raw = input(f"Enter your choice (1-{len(options)}) or type the exact value: ").strip()
                        try:
                            idx = int(raw)
                            if 1 <= idx <= len(options):
                                item_specifics[name] = options[idx - 1]['localizedValue']
                                break
                            else:
                                print("Invalid choice. Please try again.")
                                continue
                        except ValueError:
                            typed = raw
                            if any(ov['localizedValue'].lower() == typed.lower() for ov in options):
                                item_specifics[name] = typed
                                break
                            print("Value not recognised. Choose a number from the list or type an exact match.")
                else:
                    while True:
                        value = input(f"Please enter a value for '{name}' (Free Text): ").strip()
                        if value:
                            item_specifics[name] = value
                            break
                        else:
                            print("This field cannot be empty. Please enter a value.")

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

