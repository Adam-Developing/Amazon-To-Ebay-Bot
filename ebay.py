# ebay.py
from __future__ import annotations
import json
import os
import re
import xml.etree.ElementTree as ET
import requests
from typing import Dict, Any
from dotenv import load_dotenv
from ui_bridge import IOBridge
from CentralFunctions import (
    categoryTreeID,
    categoryID,
    get_item_specifics,
    set_seller_note,
    find_minimum_price,
    map_one_dict,
)

load_dotenv()


# Helper: choose the most actionable part of an eBay error message
def _choose_error_message(short: str, long: str) -> str:
    """
    Prefer the more detailed/last part of the error. Strategy:
    - If long exists and is different, prefer long.
    - If combined (short + ' - ' + long) contains ' - ', take the last segment.
    - Otherwise fall back to the last sentence (split on .!?), trim and return.
    """
    s = (short or "").strip()
    l = (long or "").strip()
    combined = " - ".join([p for p in [s, l] if p])
    # If combined contains ' - ' prefer the last segment
    if ' - ' in combined:
        candidate = combined.split(' - ')[-1].strip()
    else:
        candidate = combined or s or l
    # If candidate contains multiple sentences, prefer the last non-empty sentence
    sentences = re.split(r'[.!?]\s*', candidate)
    for sent in reversed(sentences):
        if sent and sent.strip():
            return sent.strip()
    return candidate


# Helper: detect a missing item specific field from a message
def _detect_missing_field(message: str) -> str | None:
    """
    Try multiple patterns to extract the missing field name, returning the field if found.
    """
    if not message:
        return None
    m = re.search(r"item specific\s+(?P<field>[A-Za-z0-9 _-]+)\s+is missing", message, re.IGNORECASE)
    if m:
        return m.group('field').strip()
    m = re.search(r"^The item specific (?P<field>[A-Za-z0-9 _-]+) is missing", message, re.IGNORECASE)
    if m:
        return m.group('field').strip()
    m = re.search(r"Add (?P<field>[A-Za-z0-9 _-]+) to this listing", message, re.IGNORECASE)
    if m:
        return m.group('field').strip()
    m = re.search(r"(?P<field>[A-Za-z0-9 _-]+) is required", message, re.IGNORECASE)
    if m:
        return m.group('field').strip()
    # Try a looser heuristic: look for "Type" or "Brand" capitalised words often used for specifics
    m = re.search(r"\b(Type|Brand|Model|Colour|Color|Size|Material|Condition)\b", message, re.IGNORECASE)
    if m:
        return m.group(0).strip()
    return None


BANNED_PHRASES = [
    r"warranty",
    r"customer support",
    r"customer service",
    r"contact us",
    r"amazon",
]
_BANNED_RE = re.compile(
    r"(?i)(" + "|".join([fr"\b{p}\b" if p.isalpha() else p for p in BANNED_PHRASES]) + r")"
)

# Rough sentence splitter: splits on ., !, ? followed by whitespace.
# Keeps punctuation attached to the sentence.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _sanitize_text_block(text: str) -> str:
    """
    Remove any sentence that contains a banned phrase.
    Works on plain text; if simple HTML is present, it still removes any matching sentences heuristically.
    """
    if not text:
        return text or ""
    # Quick accept: if nothing matches, return original to avoid mangling spacing.
    if not _BANNED_RE.search(text):
        return text

    # Split into sentences, filter, and rejoin with a single space.
    parts = _SENTENCE_SPLIT_RE.split(text.strip())
    kept = [s for s in parts if not _BANNED_RE.search(s)]
    return " ".join(kept).strip()


def esc_xml(s: str) -> str:
    return (s or "").replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def list_on_ebay(data: Dict[str, Any], io: IOBridge) -> Dict[str, Any]:
    io.log("Preparing eBay listing payload…")

    amazon_open = False

    raw_title = data.get('Title', 'N/A')
    if len(raw_title) > 80:
        raw_title = raw_title[:80]
    title_variable = esc_xml(raw_title)
    tempDeal_variable = bool(data.get('tempDeal', False))

    if title_variable == 'N/A':
        amazonUrl = data.get("URL", "Unknown")
        if amazonUrl != "Unknown":
            io.open_url(amazonUrl)
            amazon_open = True
        title_variable = esc_xml(io.prompt_text('What is the title:', default="").strip())

    try:
        price_variable = float(data.get('Price', -1.0))
    except Exception:
        price_variable = -1.0

    if price_variable == -1.0:
        if not amazon_open:
            amazonUrl = data.get("URL", "Unknown")
            if amazonUrl != "Unknown":
                io.open_url(amazonUrl)
                amazon_open = True
        entered = io.prompt_text("What is the price:", default="").strip()
        try:
            price_variable = float(entered)
        except Exception:
            price_variable = -1.0

    discount_value_variable = float(data.get('discount_value', -1.0) or -1.0)
    discount_type_variable = data.get("discount_type", "percentage")

    if discount_value_variable != -1.0:
        if discount_type_variable == "percentage":
            price_variable = price_variable - (price_variable * discount_value_variable)
        elif discount_type_variable == "fixed":
            price_variable = price_variable - discount_value_variable

    # Ensure Amazon page is open before manual price adjustments (<6 etc)
    if not amazon_open:
        amazonUrl = data.get("URL", "Unknown")
        if amazonUrl != "Unknown":
            io.open_url(amazonUrl)
            amazon_open = True

    if price_variable > 6:
        price_variable -= 1
    elif 0 < price_variable < 6:
        # Price is small — ask how much to take off (original behavior).
        # Include the sell price suggestion in brackets (formatted to 2 decimals).
        suggested = f"{price_variable:.2f}"
        prompt = f"Price is less than 6, what should we take off? (Currently at: £{suggested})"
        off = io.prompt_text(prompt, default="0").strip()
        try:
            price_variable -= float(off)
            # Round to 2 decimals to keep prices neat
            price_variable = round(price_variable, 2)
        except Exception:
            # ignore invalid input and leave price_variable as-is
            pass

    if bool(os.getenv("SELLER_PAY_FEE").lower() == "true"):
        price_variable = find_minimum_price(price_variable)

    # Quantity & Seller note (prefer JSON if present)
    try:
        ebayQuantity = int(data.get('quantity', 1))
    except Exception:
        qtxt = io.prompt_text("What is the quantity:", default="1").strip()
        try:
            ebayQuantity = int(qtxt)
        except Exception:
            ebayQuantity = 1
    seller_note = str(data.get('sellerNote', '') or "").strip()

    image_urls_array = data.get('imageUrls', []) or []

    # --- HTML Description ---
    # --- HTML Description ---
    html_description = f"<h1>{title_variable}</h1> <br>"

    product_overview = data.get('productOverview', {}) or {}
    if product_overview:
        html_description += '<table style="border: none; border-collapse: collapse;">'
        for key, value in product_overview.items():
            safe_val = _sanitize_text_block(str(value))
            if not safe_val:
                continue  # skip empty after sanitising
            html_description += (
                f'<tr><td style="border: none;"><b>{esc_xml(str(key))}:</b></td>'
                f'<td style="border: none;">{esc_xml(safe_val)}</td></tr>'
            )
        html_description += '</table><br>'

    featured_bullets = data.get('featuredBullets', []) or []
    if featured_bullets:
        # Filter bullets that contain banned phrases (and sanitize sentences inside)
        cleaned_bullets = []
        for item in featured_bullets:
            if not item:
                continue
            if _BANNED_RE.search(item):
                # Either drop whole bullet, or sanitise the sentences and keep if anything remains.
                sanitised = _sanitize_text_block(item)
                if sanitised:
                    cleaned_bullets.append(sanitised)
            else:
                cleaned_bullets.append(item)
        if cleaned_bullets:
            html_description += '<ul>'
            for item in cleaned_bullets:
                html_description += f'<li>{esc_xml(item)}</li>'
            html_description += '</ul><br>'

    prod_details = data.get('prodDetails', {}) or {}
    if prod_details:
        html_description += '<table style="background-color: #f2f2f2; border: 1px solid black; border-collapse: collapse; color: black;">'
        for key, value in prod_details.items():
            safe_val = _sanitize_text_block(str(value))
            if not safe_val:
                continue
            html_description += (
                f'<tr><td style="border: 1px solid black; padding: 5px;"><b>{esc_xml(str(key))}</b></td>'
                f'<td style="border: 1px solid black; padding: 5px;">{esc_xml(safe_val)}</td></tr>'
            )
        html_description += '</table>'

    important_information = data.get('importantInformation', "") or ""
    if important_information:
        safe_info = _sanitize_text_block(important_information)
        if safe_info:
            html_description += safe_info

    detail_Bullets = data.get('detailBullets', {}) or {}
    if detail_Bullets:
        html_description += '<table style="border: none; border-collapse: collapse;">'
        for key, value in detail_Bullets.items():
            safe_val = _sanitize_text_block(str(value))
            if not safe_val:
                continue
            html_description += (
                f'<tr><td style="border: none;"><b>{esc_xml(str(key))}</b></td>'
                f'<td style="border: none;">{esc_xml(safe_val)}</td></tr>'
            )
        html_description += '</table><br>'

    # --- Credentials & tokens ---
    app_id = os.getenv("EBAY_CLIENT_ID")
    cert_id = os.getenv("EBAY_CLIENT_SECRET")
    dev_id = os.getenv("EBAY_DEV_ID")

    try:
        with open('ebay_tokens.json', 'r', encoding='utf-8') as f:
            tokens = json.load(f)
        user_token = tokens['user_token']['access_token']
        applicationToken = tokens['application_token']['access_token']
    except (FileNotFoundError, KeyError) as e:
        io.log(
            f"ERROR: Token file (ebay_tokens.json) is missing or malformed: {e}. Use the GUI to initialize tokens first.")
        return {"ok": False, "error": "missing_tokens"}

    # Category & specifics discovery
    categoryTree = categoryTreeID(applicationToken)
    catID = categoryID(applicationToken, categoryTree, title_variable)
    if not amazon_open:
        amazonUrl = data.get("URL", "Unknown")
        if amazonUrl != "Unknown":
            io.open_url(amazonUrl)
            amazon_open = True

    itemSpecifics = get_item_specifics(applicationToken, categoryTree, catID, data, io)

    # Merge in custom specifics from JSON
    custom_json_specifics = data.get('customSpecifics', {}) or {}
    if isinstance(custom_json_specifics, dict):
        itemSpecifics.update(map_one_dict(custom_json_specifics))

    # Prepare mutable flags that may be changed if eBay returns policy conflicts
    auto_pay = True
    best_offer_enabled = True

    # Helper to build XML body from current variables (rebuilds item specifics each attempt)
    def build_xml_body():
        item_specifics_xml = "<ItemSpecifics>"
        for name, value in itemSpecifics.items():
            escaped_value = esc_xml(str(value))
            item_specifics_xml += f"<NameValueList><Name>{esc_xml(str(name))}</Name><Value>{escaped_value}</Value></NameValueList>"
        item_specifics_xml += "</ItemSpecifics>"

        picture_xml = ""
        if image_urls_array:
            picture_xml += "<PictureDetails>"
            for url in image_urls_array:
                picture_xml += f"<PictureURL>{esc_xml(url)}</PictureURL>"
            picture_xml += "</PictureDetails>"

        best_offer_fragment = f"<BestOfferDetails><BestOfferEnabled>{'true' if best_offer_enabled else 'false'}</BestOfferEnabled></BestOfferDetails>"
        auto_pay_fragment = f"<AutoPay>{'true' if auto_pay else 'false'}</AutoPay>"

        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<AddItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{user_token}</eBayAuthToken>
  </RequesterCredentials>
  <Item>
    <Title>{title_variable}</Title>
    <Description><![CDATA[{html_description}]]></Description>
    <PrimaryCategory><CategoryID>{catID}</CategoryID></PrimaryCategory>
    <StartPrice>{price_variable}</StartP rice>
    <CategoryMappingAllowed>true</CategoryMappingAllowed>
    <Country>GB</Country>
    <Currency>GBP</Currency>
    <ConditionID>1000</ConditionID>
    {item_specifics_xml}
    <DispatchTimeMax>3</DispatchTimeMax>
    <ListingDuration>GTC</ListingDuration>
    <ListingType>FixedPriceItem</ListingType>
    <Location>Birmingham</Location>
    <PostalCode>B14 6PA</PostalCode>
    <Quantity>{ebayQuantity}</Quantity>
    {auto_pay_fragment}
    {best_offer_fragment}
    {picture_xml}
    <ReturnPolicy><ReturnsAcceptedOption>ReturnsNotAccepted</ReturnsAcceptedOption></ReturnPolicy>
    <ShippingDetails>
      <ShippingType>Flat</ShippingType>
      <ShippingServiceOptions>
        <ShippingService>UK_RoyalMailSecondClassStandard</ShippingService>
        <ShippingServiceCost>0.00</ShippingServiceCost>
        <ShippingServiceAdditionalCost>0.00</ShippingServiceAdditionalCost>
        <FreeShipping>true</FreeShipping>
        <ShippingServicePriority>1</ShippingServicePriority>
      </ShippingServiceOptions>
      <ShippingServiceOptions>
        <ShippingService>UK_CollectInPerson</ShippingService>
        <ShippingServiceCost>0.00</ShippingServiceCost>
        <ShippingServiceAdditionalCost>0.00</ShippingServiceAdditionalCost>
        <ShippingServicePriority>2</ShippingServicePriority>
      </ShippingServiceOptions>
    </ShippingDetails>
  </Item>
</AddItemRequest>
"""
        return xml

    # Attempt loop: try to submit, and if eBay reports actionable errors (field-specific), prompt user and retry
    max_attempts = 4
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        xml_body = build_xml_body()

        endpoint = "https://api.ebay.com/ws/api.dll"
        headers = {
            "X-EBAY-API-CALL-NAME": "AddItem",
            "X-EBAY-API-SITEID": "3",
            "X-EBAY-API-APP-NAME": app_id,
            "X-EBAY-API-DEV-NAME": dev_id,
            "X-EBAY-API-CERT-NAME": cert_id,
            "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
            "Content-Type": "text/xml"
        }

        io.log("Sending eBay AddItem request…")
        response = requests.post(endpoint, data=xml_body.encode('utf-8'), headers=headers)
        io.log(f"HTTP Status Code: {response.status_code}")

        result: Dict[str, Any] = {"ok": False, "status": response.status_code, "response": response.text}

        try:
            tree = ET.fromstring(response.content)
            namespace = '{urn:ebay:apis:eBLBaseComponents}'
            ack_el = tree.find(f'{namespace}Ack')
            ack = ack_el.text if ack_el is not None else "Unknown"

            if ack in ['Success', 'Warning']:
                io.log(f"API Call successful: {ack}")
                item_id_element = tree.find(f'{namespace}ItemID')
                if item_id_element is not None:
                    item_id = item_id_element.text
                    io.log(f"New Item ID: {item_id}")
                    if seller_note:
                        set_seller_note(item_id, seller_note, user_token, app_id, dev_id, cert_id, io)
                    io.log("Opening the revise item page…")
                    revise_url = f"https://www.ebay.co.uk/sl/list?mode=ReviseItem&itemId={item_id}&ReturnURL=https%3A%2F%2Fwww.ebay.co.uk%2Fsh%2Flst%2Factive%3Foffset%3D0"
                    io.open_url(revise_url)
                    result.update({"ok": True, "ack": ack, "item_id": item_id})
                else:
                    io.log("Listing succeeded, but no ItemID found in response.")
                    result.update({"ok": True, "ack": ack, "item_id": None})
                return result
            else:
                # Parse errors and try to handle actionable ones
                io.log(f"API Call failed with status: {ack}")
                errors = []
                for error in tree.findall(f'{namespace}Errors'):
                    short_message_el = error.find(f'{namespace}ShortMessage')
                    long_message_el = error.find(f'{namespace}LongMessage')
                    short_message = short_message_el.text if short_message_el is not None else ""
                    long_message = long_message_el.text if long_message_el is not None else ""
                    io.log(f"Error: {short_message} - {long_message}")
                    errors.append({"short": short_message, "long": long_message})

                # Pre-scan errors to see if there's any actionable problem other than Best Offer/AutoPay conflicts.
                # If so, we'll skip prompting about Best Offer and handle the other errors first.
                has_other_actionable = False
                for e in errors:
                    _short = e.get('short', '') or ''
                    _long = e.get('long', '') or ''
                    _actionable = _choose_error_message(_short, _long)
                    # Missing specific
                    if _detect_missing_field(_actionable):
                        has_other_actionable = True
                        break
                    # Field length/value errors
                    if re.search(r"(?P<field>[\w ]+)'s value of \"(?P<value>.+?)\" is too (long|short)", _long,
                                 re.IGNORECASE):
                        has_other_actionable = True
                        break
                    # Generic 'too many characters' pattern
                    if re.search(r'"(?P<val>.{10,})" has too many characters|too many characters.*\"(?P<val2>.+?)\"',
                                 _long, re.IGNORECASE):
                        has_other_actionable = True
                        break

                # Try to detect field-specific errors like: "Type's value of \"...\" is too long. Enter a value of no more than 65 characters."
                handled_any = False
                for err in errors:
                    long = err.get('long', '') or ''
                    short = err.get('short', '') or ''

                    # Prefer the most actionable fragment for decision-making
                    actionable = _choose_error_message(short, long)

                    # Detect missing specifics first
                    missing = _detect_missing_field(actionable)
                    if missing:
                        # Ask the user for the missing specific and insert into itemSpecifics
                        prompt = f"eBay reports a missing item specific: '{missing}'. Please provide a value for '{missing}':"
                        value = io.prompt_text(prompt, default="").strip()
                        if not value:
                            io.log(f"User did not provide a value for required specific '{missing}'; aborting.")
                            return {"ok": False, "ack": ack, "errors": errors}
                        # Find a matching key (case-insensitive) or add new
                        matched = None
                        for k in list(itemSpecifics.keys()):
                            if k.lower() == missing.lower() or missing.lower() in k.lower() or k.lower() in missing.lower():
                                matched = k
                                break
                        if matched:
                            itemSpecifics[matched] = value
                        else:
                            itemSpecifics[missing] = value
                        io.log(f"Added missing item specific '{missing}': '{value}'. Retrying.")
                        handled_any = True
                        break

                    # Best Offer vs AutoPay conflict (use actionable text)
                    if re.search(r"Best Offer.*immediate payment|immediate payment.*Best Offer",
                                 actionable + ' ' + short, re.IGNORECASE):
                        # If there are other actionable errors, skip resolving Best Offer now so we can address them first.
                        if has_other_actionable:
                            io.log(
                                "Skipping Best Offer/AutoPay policy prompt because other actionable errors are present; resolving those first.")
                            continue
                        choice = io.prompt_choice(
                            "eBay reports a policy conflict: If this item sells by a Best Offer, you will not be able to require immediate payment.\nChoose how to proceed:",
                            ["Disable Best Offer", "Disable Immediate Payment", "Cancel"]
                        )
                        if choice == "Disable Best Offer":
                            best_offer_enabled = False
                            io.log("User chose to disable Best Offer and retry.")
                            handled_any = True
                            break
                        elif choice == "Disable Immediate Payment":
                            auto_pay = False
                            io.log("User chose to disable immediate payment (AutoPay) and retry.")
                            handled_any = True
                            break
                        else:
                            io.log("User cancelled while resolving policy conflict.")
                            return {"ok": False, "ack": ack, "errors": errors}

                    # Field length or value errors (use 'long' original matching as before)
                    m = re.search(r"(?P<field>[\w ]+)'s value of \"(?P<value>.+?)\" is too (?P<issue>long|short)", long,
                                  re.IGNORECASE)
                    if m:
                        field = m.group('field').strip()
                        current_value = m.group('value')
                        # Try to extract a max length constraint if present
                        max_m = re.search(r"Enter a value of no more than (?P<max>\d+) characters", long, re.IGNORECASE)
                        max_len = int(max_m.group('max')) if max_m else None
                        prompt = f"eBay error for field '{field}': {short} - {long}\nEnter a new value for '{field}':"
                        default = current_value
                        if max_len:
                            prompt += f" (max {max_len} characters)"
                        new_val = io.prompt_text(prompt, default=default).strip()
                        if new_val == default and len(default) > (max_len or 1000):
                            # If user didn't change and it's still too long, truncate to allowed length
                            if max_len:
                                new_val = default[:max_len]
                                io.log(f"Automatically truncating value for '{field}' to {max_len} characters.")
                        if not new_val:
                            io.log(f"User provided empty value for '{field}'; aborting.")
                            return {"ok": False, "ack": ack, "errors": errors}

                        # Assign the corrected value into the right place
                        fname_lower = field.lower()
                        if fname_lower == 'title':
                            title_variable = esc_xml(new_val)
                        elif fname_lower in ('price', 'startprice'):
                            try:
                                price_variable = float(new_val)
                            except Exception:
                                io.log(f"Provided value for '{field}' is not a valid number: {new_val}")
                                return {"ok": False, "ack": ack, "errors": errors}
                        elif fname_lower in ('quantity',):
                            try:
                                ebayQuantity = int(new_val)
                            except Exception:
                                io.log(f"Provided value for '{field}' is not a valid integer: {new_val}")
                                return {"ok": False, "ack": ack, "errors": errors}
                        else:
                            # Treat as an item specific: update existing key if case-insensitive match, else add new
                            matched = None
                            for k in list(itemSpecifics.keys()):
                                if k.lower() == fname_lower or fname_lower in k.lower() or k.lower() in fname_lower:
                                    matched = k
                                    break
                            if matched:
                                itemSpecifics[matched] = new_val
                            else:
                                # Create/update the raw field name
                                itemSpecifics[field] = new_val
                        handled_any = True
                        break

                    # Generic 'too many characters' fallback: try to find a quoted value in the message
                    q = re.search(r'"(?P<val>.{10,})" has too many characters|too many characters.*\"(?P<val2>.+?)\"',
                                  long, re.IGNORECASE)
                    if q:
                        current_value = q.group('val') if q.group('val') else q.group('val2')
                        prompt = f"eBay reports a value that's too long: {short} - {long}\nPlease provide a corrected value (current shown):"
                        new_val = io.prompt_text(prompt, default=current_value).strip()
                        if not new_val:
                            return {"ok": False, "ack": ack, "errors": errors}
                        # Attempt to place into item specifics (best-effort)
                        # If we can find which specific matches current_value, replace it
                        replaced = False
                        for k, v in list(itemSpecifics.items()):
                            if str(v) == current_value:
                                itemSpecifics[k] = new_val
                                replaced = True
                                break
                        if not replaced:
                            itemSpecifics[f'Corrected'] = new_val
                        handled_any = True
                        break

                if not handled_any:
                    io.log("Unrecognised eBay errors; not prompting for corrections.")
                    return {"ok": False, "ack": ack, "errors": errors}
                # If we handled an error, loop will retry building xml and resubmitting
        except ET.ParseError:
            io.log("Could not parse the XML response from eBay.")
            return {"ok": False, "error": "parse_error"}

    # If we exhausted attempts
    io.log("Exceeded maximum retries attempting to correct eBay errors.")
    return {"ok": False, "error": "max_retries"}
