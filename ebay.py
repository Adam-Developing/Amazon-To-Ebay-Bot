# ebay.py
from __future__ import annotations
import json
import os
import re
import webbrowser
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
    merge_specifics_in_order,
)

load_dotenv()

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

    title_variable = esc_xml(data.get('Title', 'N/A'))
    tempDeal_variable = bool(data.get('tempDeal', False))

    if title_variable == 'N/A':
        amazonUrl = data.get("URL", "Unknown")
        if amazonUrl != "Unknown":
            io.open_url(amazonUrl);
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
                io.open_url(amazonUrl);
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
            io.open_url(amazonUrl);
            amazon_open = True

    if price_variable > 6:
        price_variable -= 1
    elif 0 < price_variable < 6:
        off = io.prompt_text("Price is less than 6, what should we take off?", default="0").strip()
        try:
            price_variable -= float(off)
        except Exception:
            pass

    if bool((os.getenv("SELLER_PAY_FEE") or "").lower() == "true"):
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
            io.open_url(amazonUrl);
            amazon_open = True

    itemSpecifics = get_item_specifics(applicationToken, categoryTree, catID, data, io)

    # Merge in custom specifics from JSON
    custom_json_specifics = data.get('customSpecifics', {}) or {}
    if isinstance(custom_json_specifics, dict):
        itemSpecifics.update(map_one_dict(custom_json_specifics))

    # Build XML fragments
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

    xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<AddItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{user_token}</eBayAuthToken>
  </RequesterCredentials>
  <Item>
    <Title>{title_variable[:80]}</Title>
    <Description><![CDATA[{html_description}]]></Description>
    <PrimaryCategory><CategoryID>{catID}</CategoryID></PrimaryCategory>
    <StartPrice>{price_variable}</StartPrice>
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
    <AutoPay>true</AutoPay>
    <BestOfferDetails><BestOfferEnabled>true</BestOfferEnabled></BestOfferDetails>
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
        else:
            io.log(f"API Call failed with status: {ack}")
            for error in tree.findall(f'{namespace}Errors'):
                short_message_el = error.find(f'{namespace}ShortMessage')
                long_message_el = error.find(f'{namespace}LongMessage')
                short_message = short_message_el.text if short_message_el is not None else ""
                long_message = long_message_el.text if long_message_el is not None else ""
                io.log(f"Error: {short_message} - {long_message}")
            result.update({"ok": False, "ack": ack})
    except ET.ParseError:
        io.log("Could not parse the XML response from eBay.")

    return result
