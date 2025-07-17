import json
import os
import webbrowser
import xml.etree.ElementTree as ET
import requests
from dotenv import load_dotenv
from CentralFunctions import categoryTreeID, categoryID, get_item_specifics, set_seller_note, find_minimum_price

# Load the JSON data from the file
# Ensure you have a 'product.json' file in the same directory
try:
    with open('product.json', 'r') as f:
        data = json.load(f)
except FileNotFoundError:
    print("Error: 'product.json' not found. Please create one.")
    exit()
# Load environment variables from .env file
load_dotenv()
# --- Variable Extraction & Formatting ---
amazonOpen = False
# escape the '&' character for XML
title_variable = data.get('Title', 'N/A').replace('&', '&amp;')
tempDeal_variable = bool(data.get('tempDeal', False))
if title_variable == 'N/A':
    amazonUrl = data.get("URL", "Unknown")
    if amazonUrl != "Unknown":
        webbrowser.open(amazonUrl)
        amazonOpen = True
    title_variable = input('What is the title: ')
price_variable = float(data.get('Price', -1.0))
if price_variable == -1.0:
    if not amazonOpen:
        amazonUrl = data.get("URL", "Unknown")
        if amazonUrl != "Unknown":
            webbrowser.open(amazonUrl)
            amazonOpen = True

    price_variable = float(input("What is the price: "))
discount_value_variable = float(data.get('discount_value', -1.0))
discount_type_variable = data.get("discount_type", "percentage")

if discount_value_variable != -1.0:
    if discount_type_variable == "percentage":
        price_variable = price_variable - (price_variable * discount_value_variable)
    elif discount_type_variable == "fixed":
        price_variable = price_variable - discount_value_variable

if tempDeal_variable:
    price_variable = float(price_variable)
elif price_variable > 6:
    price_variable -= 1
elif price_variable < 6:
    price_variable -= input("Price is less than 6, what should we take off? ")

if bool(os.getenv("SELLER_PAY_FEE")):
    price_variable = find_minimum_price(price_variable)

ebayQuantity = input("What is the quantity: ")
if ebayQuantity.isdigit():
    ebayQuantity = int(ebayQuantity)
else:
    ebayQuantity = 1
seller_note = input("Enter a private seller note (optional, press Enter to skip): ").strip()

image_urls_array = data.get('imageUrls', [])

# --- HTML Description Generation (Corrected) ---

# Start directly with the first element, like the <h1> title.
# DO NOT include <!DOCTYPE>, <html>, <head>, or <body> tags.

html_description = f"<h1>{title_variable}</h1> <br>"

product_overview = data.get('productOverview', {})
if product_overview:
    html_description += '<table style="border: none; border-collapse: collapse;">'
    for key, value in product_overview.items():
        # Using single quotes for the f-string to avoid escaping issues
        html_description += f'<tr><td style="border: none;"><b>{key}:</b></td><td style="border: none;">{value}</td></tr>'
    html_description += '</table><br>'

featured_bullets = data.get('featuredBullets', [])
if featured_bullets:
    html_description += '<ul>'
    for item in featured_bullets:
        html_description += f'<li>{item}</li>'
    html_description += '</ul><br>'

prod_details = data.get('prodDetails', {})
if prod_details:
    html_description += '<table style="background-color: #f2f2f2; border: 1px solid black; border-collapse: collapse; color: black;">'
    for key, value in prod_details.items():
        html_description += f'<tr><td style="border: 1px solid black; padding: 5px;"><b>{key}</b></td><td style="border: 1px solid black; padding: 5px;">{value}</td></tr>'
    html_description += '</table>'
important_information = data.get('importantInformation', "")

if important_information:
    html_description += important_information

detail_Bullets = data.get('detailBullets', {})
if detail_Bullets:
    html_description += '<table style="border: none; border-collapse: collapse;">'
    for key, value in detail_Bullets.items():
        # Using single quotes for the f-string to avoid escaping issues
        html_description += f'<tr><td style="border: none;"><b>{key}</b></td><td style="border: none;">{value}</td></tr>'
    html_description += '</table><br>'

# --- eBay API Call ---

# Your Production Credentials


# Load static credentials from environment variables
app_id = os.getenv("EBAY_CLIENT_ID")
cert_id = os.getenv("EBAY_CLIENT_SECRET")
dev_id = os.getenv("EBAY_DEV_ID")

# Load dynamic tokens from the JSON file created by the runner
try:
    with open('ebay_tokens.json', 'r') as f:
        tokens = json.load(f)
    # The token for the Trading API (AddItem) is the user access token
    user_token = tokens['user_token']['access_token']
    # The token for the RESTful APIs (get_item_specifics) is the application token
    applicationToken = tokens['application_token']['access_token']
except (FileNotFoundError, KeyError) as e:
    print(
        f"❌ ERROR: Token file (ebay_tokens.json) is missing or malformed: {e}. Please run the main runner script first.")
    exit()

categoryTreeID = categoryTreeID(applicationToken)
categoryID = categoryID(applicationToken, categoryTreeID, title_variable)
if not amazonOpen:
    amazonUrl = data.get("URL", "Unknown")
    if amazonUrl != "Unknown":
        webbrowser.open(amazonUrl)
        amazonOpen = True

itemSpecifics = get_item_specifics(applicationToken, categoryTreeID, categoryID, data)

# --- Add Custom Item Specifics ---
print("\n--- Adding Custom Item Specifics ---")
print("Add any extra item specifics. Press Enter at the 'name' prompt when finished.")
while True:
    name = input("Enter custom specific name (or press Enter to finish): ").strip()
    if not name:
        break
    value = input(f"Enter value for '{name}': ").strip()
    # Only add the specific if both name and value are provided
    if name and value:
        itemSpecifics[name] = value
    else:
        print("Both name and value are required. Specific not added.")

item_specifics_xml = "<ItemSpecifics>"
for name, value in itemSpecifics.items():
    escaped_value = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    item_specifics_xml += f"<NameValueList><Name>{name}</Name><Value>{escaped_value}</Value></NameValueList>"
item_specifics_xml += "</ItemSpecifics>"

# Dynamically create the <PictureDetails> block
picture_xml = ""
if image_urls_array:
    picture_xml += "<PictureDetails>"
    for url in image_urls_array:
        # Ensure '&' is escaped in image URLs as well
        picture_xml += f"<PictureURL>{url.replace('&', '&amp;')}</PictureURL>"
    picture_xml += "</PictureDetails>"

# XML body for AddItemRequest
xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<AddItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{user_token}</eBayAuthToken>
  </RequesterCredentials>
  <Item>
    <Title>{title_variable[:80]}</Title>
    <Description>
      <![CDATA[{html_description}]]>
    </Description>
    <PrimaryCategory>
      <CategoryID>{categoryID}</CategoryID>
    </PrimaryCategory>
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
    
    <BestOfferDetails>
      <BestOfferEnabled>true</BestOfferEnabled>
    </BestOfferDetails>

    {picture_xml}

    <ReturnPolicy>
        <ReturnsAcceptedOption>ReturnsNotAccepted</ReturnsAcceptedOption>
    </ReturnPolicy>

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

# --- API Request and Response Handling ---
endpoint = "https://api.ebay.com/ws/api.dll"
headers = {
    "X-EBAY-API-CALL-NAME": "AddItem",
    "X-EBAY-API-SITEID": "3",  # 3 = UK
    "X-EBAY-API-APP-NAME": app_id,
    "X-EBAY-API-DEV-NAME": dev_id,
    "X-EBAY-API-CERT-NAME": cert_id,
    "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
    "Content-Type": "text/xml"
}

print("--- Sending API Request ---")
response = requests.post(endpoint, data=xml_body.encode('utf-8'), headers=headers)

print(f"HTTP Status Code: {response.status_code}")

# Parse the XML response to find the ItemID
try:
    tree = ET.fromstring(response.content)
    namespace = '{urn:ebay:apis:eBLBaseComponents}'
    ack = tree.find(f'{namespace}Ack').text

    if ack in ['Success', 'Warning']:
        print(f"✅ API Call successful with status: {ack}")
        item_id_element = tree.find(f'{namespace}ItemID')

        if item_id_element is not None:
            item_id = item_id_element.text
            print(f"   New Item ID: {item_id}")
            if seller_note:
                set_seller_note(item_id, seller_note, user_token, app_id, dev_id, cert_id)

            # Construct the revise URL and open it in the browser
            print("   Opening the revise item page...")
            revise_url = f"https://www.ebay.co.uk/sl/list?mode=ReviseItem&itemId={item_id}&ReturnURL=https%3A%2F%2Fwww.ebay.co.uk%2Fsh%2Flst%2Factive%3Foffset%3D0"
            webbrowser.open(revise_url)
        else:
            print("   Listing was successful, but no ItemID was found in the response.")

    else:
        print(f"❌ API Call failed with status: {ack}")
        for error in tree.findall(f'{namespace}Errors'):
            short_message = error.find(f'{namespace}ShortMessage').text
            long_message = error.find(f'{namespace}LongMessage').text
            print(f"   Error: {short_message} - {long_message}")

except ET.ParseError:
    print("❌ Could not parse the XML response from eBay.")
    print("\n--- Full Response ---")
print(response.text)
