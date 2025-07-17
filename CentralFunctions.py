import json
import os

import requests
import xml.etree.ElementTree as ET

from dotenv import load_dotenv

load_dotenv()


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
    Gets required and custom aspects for a category. It prioritises a bulk-pasted
    string for custom values, then finds API-defined aspects in product_data,
    and finally, interactively asks for any remaining required aspects.
    """
    headers = {'Authorization': f'Bearer {token}'}
    url = f"https://api.ebay.com/commerce/taxonomy/v1/category_tree/{category_tree_id}/get_item_aspects_for_category?category_id={category_id}"

    # This will hold the final list of specifics
    item_specifics = {}

    try:
        print("\n--- Populating Item Specifics ---")

        # --- 1. Process Bulk/Custom Specifics First ---
        pasted_string = input(
            "Paste custom specifics (e.g., Name: Value | Name: Value) or press Enter: "
        ).strip()

        if pasted_string:
            pairs = pasted_string.split('|')
            for pair in pairs:
                if ':' in pair:
                    # Split only on the first colon
                    key, value = pair.split(':', 1)
                    clean_key = key.strip()
                    clean_value = value.strip()
                    if clean_key and clean_value:
                        item_specifics[clean_key] = clean_value
            print("✅ Added custom specifics from pasted text.")

        # --- 2. Fetch and Process API-defined Aspects ---
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Prepare lowercase versions of product data for case-insensitive matching
        prod_details = {k.lower(): v for k, v in product_data.get('prodDetails', {}).items()}
        prod_overview = {k.lower(): v for k, v in product_data.get('productOverview', {}).items()}

        for aspect in data.get('aspects', []):
            name = aspect['localizedAspectName']
            name_lower = name.lower()
            is_required = aspect.get('aspectConstraint', {}).get('aspectRequired', False)

            # If this aspect was already provided in the custom paste, skip it
            if name in item_specifics:
                print(f"Using custom value for '{name}': {item_specifics[name]}")
                continue

            # --- Search Order for remaining: 1. product.json -> 2. Ask User ---
            found_value = prod_details.get(name_lower) or prod_overview.get(name_lower)
            if found_value:
                item_specifics[name] = found_value
                print(f"Found '{name}' from product.json: {found_value}")
                continue

            # If not found automatically, and it's required, ask the user
            if is_required:
                print(f"\n❓ Required aspect '{name}' not found automatically.")
                mode = aspect.get('aspectConstraint', {}).get('aspectMode')

                if mode == 'SELECTION_ONLY' and aspect.get('aspectValues'):
                    options = aspect['aspectValues']
                    print(f"Please select one for '{name}':")
                    for i, option in enumerate(options):
                        print(f"  {i + 1}: {option['localizedValue']}")
                    while True:
                        try:
                            choice = int(input(f"Enter your choice (1-{len(options)}): "))
                            if 1 <= choice <= len(options):
                                item_specifics[name] = options[choice - 1]['localizedValue']
                                break
                            else:
                                print("Invalid choice. Please try again.")
                        except ValueError:
                            print("Invalid input. Please enter a number.")
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

