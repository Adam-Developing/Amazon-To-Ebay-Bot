import os
import json
import base64
import re
import time

import paramiko
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver import ActionChains, Keys
from selenium.webdriver.common.by import By
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

allAspects = {}

quantity = input('What is the quantity?')
quantity = int(quantity)
l = None
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'}
i = 1
images = []

url = input('Please enter the link ')
options = webdriver.ChromeOptions()
options.add_experimental_option("detach", True)
# options.add_argument('--headless')
# options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36')
driver = webdriver.Chrome(options=options)
driver.get(url)

driver.maximize_window()


def remove_class_attribute(input_string):
    # Regular expression to find class attribute with any value
    class_pattern = r' class="[^"]*"'

    # Use re.sub() to replace the class attribute with an empty string
    descripriond = re.sub(class_pattern, '', input_string)

    return descripriond


def pageLoad():
    try:
        driver.find_element(By.XPATH, value='//*[@id="sp-cc-accept"]')
    except AttributeError:
        pageLoad()


driver.find_element(By.XPATH, value='//*[@id="sp-cc-accept"]').click()

# html = requests.get(url, headers=headers)
html = driver.page_source
s = BeautifulSoup(html, 'html.parser')

sftp_host = os.getenv("sftp_host") # Replace this with the SFTP server hostname
webURL="https://"+sftp_host+"/"
sftp_port = os.getenv("sftp_port") # Replace this with the SFTP server port
sftp_port = int(sftp_port)
sftp_username = os.getenv("sftp_username") # Replace this with your SFTP username
sftp_password = os.getenv("sftp_password") # Replace this with your SFTP password
remote_path_image = os.getenv("remote_path_image") # Replace this with the remote path on the SFTP server


title = s.find(id='productTitle').get_text(strip=True)
titlec = "<h1>" + title + "</h1>"
try:
    Brand = s.find(id='bylineInfo').get_text(strip=True)
    Brand = Brand.replace('Brand: ', '')
except AttributeError:
    Brand = ""
if len(title) > 79:
    title80 = title[0:80]
    print(title80)
print(title)
price = s.find("span", {"class": "a-offscreen"}).text
price = price.replace('£', '')
price = float(price)

if price < 5.49:
    price = str(price)
    price = input("The amazon price is £" + price + " what should the new price be?")
    price = float(price)
elif 5.5 <= price <= 10:
    price = price - 0.5
elif price > 11.5:
    price = price - 1.5
print(price)
a = ActionChains(driver)

try:
    description1 = s.find("div", {"class": "a-expander-content a-expander-partial-collapse-content"})
    description1 = str(description1)
    description1 = remove_class_attribute(description1)

    print(description1)
except (AttributeError):
    description1 = ""

try:
    description2 = s.find("table", {"class": "a-normal a-spacing-micro"})
    description2 = str(description2)
    description2 = remove_class_attribute(description2)
    print(description2)
except AttributeError:
    description2 = ""

try:
    description3 = s.find("ul", {"class": "a-unordered-list a-vertical a-spacing-mini"})
    description3 = str(description3)
    description3 = remove_class_attribute(description3)
    print(description3)
except AttributeError:
    description3 = ""
try:
    description4 = s.find(id='productDetails_techSpec_section_1')
    description4 = str(description4)
    description4 = remove_class_attribute(description4)
    print(description4)
except AttributeError:
    description4 = ""

# try:
description5 = s.find(id="aplus_feature_div")
description5 = str(description5)
description5 = remove_class_attribute(description5)
lines = description5.split('\n')
cleaned_lines = []

for line in lines:
    if line.strip().startswith('.'):
        cleaned_lines.append(' ')
    else:
        index = line.find('. ')
        if index != -1:
            cleaned_lines.append(line[:index + 1])
        else:
            cleaned_lines.append(line)
description5 = '\n'.join(cleaned_lines)
lines = description5.split('\n')
cleaned_lines = []

for line in lines:
    if line.strip().startswith("html[dir='rtl']"):
        cleaned_lines.append(" ")
    else:
        index = line.find("html[dir='rtl']")
        if index != -1:
            cleaned_lines.append(line[:index] + "html[dir='rtl']")
        else:
            cleaned_lines.append(line)

description5 = '\n'.join(cleaned_lines)

description5 = BeautifulSoup(description5, 'html.parser')

# soup = BeautifulSoup('<script>a</script>baba<script>b</script>', 'html.parser')
for s in description5.select('script'):
    s.extract()
for s in description5.select('style'):
    s.extract()
print(description5)
description = str(titlec) + "<br>" + str(description1) + "<br>" + str(description2) + "<br>" + str(description3) + "<br>" + str(description4) + "<br>" + str(description5)
s = BeautifulSoup(html, 'html.parser')
def skuFunction():
    global sku

    with open("sku.txt", "rb") as file:
        try:
            file.seek(-2, os.SEEK_END)
            while file.read(1) != b'\n':
                file.seek(-2, os.SEEK_CUR)
        except OSError:
            file.seek(0)
        skul = file.readline().decode()
    skul = int(skul)
    sku = skul + 1
    with open("sku.txt", "a") as a_file:
        sku = str(sku)
        a_file.write("\n")
        a_file.write(sku)
    print(sku)

skuFunction()
if len(description) >= 4000:
    description5ImgSource=[]

    #description5up = s.find(id="aplus_feature_div")
    #print(description5up)

    #description5HTML = BeautifulSoup(description5, "html.parser")
    description5Images=description5.findAll("img")
    for image in description5Images:
        description5ImgSource.append(image['src'])
    description5ImgSource=[item for item in description5ImgSource if item not in 'https://images-na.ssl-images-amazon.com/images/G/01/x-locale/common/grey-pixel.gif']
    description5 = str(description5.get_text(strip=True))
    for imagei in description5ImgSource:
        print(imagei)
        try:
            #myServerImageResponse = requests.get(imagei)
            #myServerImageResponse.raise_for_status()  # Check for any errors in the response
            #image_data=myServerImageResponse.content
            #print(image_data)
            try:
                ssh_client = paramiko.SSHClient()
                ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh_client.connect(sftp_host, port=sftp_port, username=sftp_username, password=sftp_password)

                with ssh_client.open_sftp() as sftp:
                    sftp.putfo(imagei, remote_path_image+sku)

                print(f"Image uploaded successfully to '{remote_path_image}' on the SFTP server.")
                imagei=webURL+sku
            except Exception as e:
                print(f"Error occurred: {e}")

            finally:
                ssh_client.close()


        except requests.exceptions.RequestException as e:
            print(f"Error occurred: {e}")

        description5=description5+'<br> <img src="'+ imagei +'">'
    print(description5)


    print('description5 too long: ' + description5)
else:
    pass


# except AttributeError:
#     description5 = ""
print(description5)

try:
    description6 = s.find(id='productDescription')
    description6 = str(description6)
    description6 = remove_class_attribute(description6)


except AttributeError:
    description6 = ""

# description5 = s.find("div",{"class": "a-expander-content a-expander-partial-collapse-content"}).text
description1 = str(description1)
description2 = str(description2)
description3 = str(description3)
description4 = str(description4)
description5 = str(description5)
description6 = str(description6)

if description1 == 'None':
    description1 = ''
else:
    pass

if description2 == 'None':
    description2 = ''
else:
    pass

if description3 == 'None':
    description3 = ''
else:
    pass

if description4 == 'None':
    description4 = ''
else:
    pass

if description5 == 'None':
    description5 = ''
else:
    pass

if description6 == 'None':
    description6 = ''
else:
    pass

print(description1)
print(description2)
print(description3)
print(description4)
print(description5)
print(description6)

try:
    driver.find_element(by='xpath', value='//*[@id="landingImage"]').click()
except NoSuchElementException:
    driver.find_element(By.XPATH, value='//*[@id="imgThumbs"]/div[1]/img').click()

# html = driver.page_source

# soup = BeautifulSoup(html, 'html.parser')
time.sleep(1)
try:
    driver.find_element(by='id', value='ivImage_0').click()
    l = 'ivImage_'
except (NoSuchElementException, ElementNotInteractableException):
    try:
        driver.find_element(by='id', value='igImage_0').click()
        l = 'igImage_'
    except NoSuchElementException:
        try:
            driver.find_element(by='id', value='ig-thumb-0').click()
            l = 'ig-thumb-'
        except NoSuchElementException:
            pass

time.sleep(1.5)
html = driver.page_source
soup = BeautifulSoup(html, 'html.parser')
try:
    image = soup.find("img", {"class": "fullscreen"}).get('src')
    k = 'fullscreen'
except (NoSuchElementException, AttributeError):
    try:
        image = soup.find("img", {"class": "image-stretch-vertical"}).get('src')
        k = 'image-stretch-vertical'
    except (NoSuchElementException, AttributeError):
        image = soup.find("img", {"class": "image-stretch-horizontal"}).get('src')
        k = 'image-stretch-horizontal'

images.append(image)
print(image)


def locateImage():
    try:
        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        image = soup.find("img", {"class": k}).get('src')
        images.append(image)
        print(image)
    except AttributeError:
        print('retry')
        locateImage()


while 1 == 1:
    try:
        c = str(i)
        if l == None:
            break
        else:

            driver.find_element(by='id', value=l + c).click()
            locateImage()
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            i = i + 1

    except NoSuchElementException:
        break
print(images)

description = str(title) + "<br>" + str(description1) + "<br>" + str(description2) + "<br>" + str(
    description3) + "<br>" + str(description4) + '<br>' + str(description5) + '<br>' + str(description6)
print(description)
#################################################### Ebay Start ####################################################
print('starting ebay now')
client_id = os.getenv("client_id")
client_secret = os.getenv("client_secret")
redirect_uri = os.getenv("redirect_uri")

auth_url = 'https://auth.ebay.com/oauth2/authorize'
token_url = 'https://api.ebay.com/identity/v1/oauth2/token'


def get_access_token(client_id, client_secret, redirect_uri):
    global access_token
    global refresh_token
    auth_code = input('Please enter the authorization code: ')
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()}'
    }
    data = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': redirect_uri
    }
    response = requests.post(token_url, headers=headers, data=data)
    access_token = json.loads(response.text)['access_token']
    refresh_token = json.loads(response.text)['refresh_token']
    print(refresh_token)
    with open('.env', 'r') as env_file:
        lines = env_file.readlines()

    lines[3] = f"access_token={access_token}\n"
    with open('.env', 'w') as file:
        file.writelines(lines)

    access_token_expire = datetime.now() + timedelta(hours=1.75)
    lines[4] = f"access_token_expire={access_token_expire}\n"
    with open('.env', 'w') as file:
        file.writelines(lines)

    lines[5] = f"refresh_token={refresh_token}\n"
    with open('.env', 'w') as file:
        file.writelines(lines)

    refresh_token_expire = datetime.now() + timedelta(days=547)
    lines[6] = f"refresh_token_expire={refresh_token_expire}"
    with open('.env', 'w') as file:
        file.writelines(lines)


def get_Refresh_Token():
    global access_token
    global refresh_token
    refresh_token = os.getenv("refresh_token")
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()}'
    }
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'scope': 'https://api.ebay.com/oauth/api_scope/sell.inventory https://api.ebay.com/oauth/api_scope'
    }
    response = requests.post(token_url, headers=headers, data=data)
    access_token = json.loads(response.text)['access_token']

    with open('.env', 'r') as env_file:
        lines = env_file.readlines()

    lines[3] = f"access_token={access_token}\n"
    with open('.env', 'w') as file:
        file.writelines(lines)

    access_token_expire = datetime.now() + timedelta(hours=1.75)
    lines[4] = f"access_token_expire={access_token_expire}\n"
    with open('.env', 'w') as file:
        file.writelines(lines)


def getCategorySuggestions(access_token):
    global categoryID
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Accept-Encoding': 'gzip'
    }

    data = {
        "location": {
            "address": {
                "city": "Birmingham",
                "country": "GB"
            }
        }
    }
    suggestionsURL = 'https://api.ebay.com/commerce/taxonomy/v1/category_tree/0/get_category_suggestions?q=' + title
    response = requests.get(suggestionsURL, headers=headers, data=json.dumps(data))
    allSuggestionsJSON = json.loads(response.text)
    categoryID = allSuggestionsJSON['categorySuggestions'][0]['category']['categoryId']

    print(categoryID)


def findRequired(access_token):
    global allAspectsJSON
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Accept-Encoding': 'gzip'
    }

    suggestionsURL = 'https://api.ebay.com/commerce/taxonomy/v1/category_tree/0/get_item_aspects_for_category?category_id=' + categoryID
    response = requests.get(suggestionsURL, headers=headers)

    allAspects = []
    # Parse the JSON data
    json_data = json.loads(response.text)

    # Iterate over the aspects
    for aspect in json_data['aspects']:
        if aspect['aspectConstraint']['aspectRequired']:
            allAspects.append(aspect['localizedAspectName'])

    # Iterate over each word in the list
    for i in allAspects:
        # Prompt the user for the meaning of the word
        if i == 'Brand':
            print(i)
            if Brand == '':
                tempAspect = input(f"What is the {i}? ")
            else:
                tempAspect = Brand
        else:
            tempAspect = input(f"What is the {i}? ")
        # Store the user input in a variable named after the current word
        locals()[i] = tempAspect

    # Print the meanings entered by the user
    for i in allAspects:
        print(f"The {i} is: {locals()[i]}")

    allAspectsJSON = {}
    print(allAspects)
    # Convert each word to a JSON array
    for aspect in allAspects:
        value = locals()[aspect]  # Get the value of the predefined variable
        allAspectsJSON[aspect] = [value]  # Create the JSON array with a single element

    # Print the JSON data


def list_item(access_token, description1, description2, description3, description4, allAspectsJSON):
    print(
        'These are the descrptions ##############################################################################################################################')
    print('description1')
    print(description1)
    print('description2')
    print(description2)
    print('description3')
    print(description3)
    print('description4')
    print(description4)
    print('description5')
    print(description5)
    print('description6')
    print(description6)


    # Print the JSON data

    # imagesJSON = json.dumps(images)
    print(images)
    print(image)
    description1 = str(description1)
    description2 = str(description2)
    description3 = str(description3)
    description4 = str(description4)

    description = str(titlec) + "<br>" + str(description1) + "<br>" + str(description2) + "<br>" + str(
        description3) + "<br>" + str(description4) + "<br>" + str(description5) + "<br>" + str(description6)
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Content-Language': 'en-GB'
    }
    data = {
        "availability": {
            "shipToLocationAvailability": {
                "quantity": quantity
            }
        },
        "condition": "NEW",
        "product": {
            "title": title80,
            "description": description,
            "aspects": allAspectsJSON,

            "imageUrls": images
        }
    }

    response = requests.put('https://api.ebay.com/sell/inventory/v1/inventory_item/' + sku, headers=headers, json=data)

    print(response.text)


def createOffer():
    global offerID
    print(sku)
    print(price)
    print(categoryID)
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Content-Language': 'en-GB'
    }
    data = {
        "sku": sku,
        "marketplaceId": "EBAY_GB",
        "format": "FIXED_PRICE",
        "pricingSummary": {
            "price": {
                "value": price,
                "currency": "GBP"
            }
        },
        "listingPolicies": {
            "fulfillmentPolicyId": "225926969013",
            "paymentPolicyId": "197467886013",
            "returnPolicyId": "223906115013",
            "bestOfferTerms":
                {
                    "bestOfferEnabled": "true"
                },
        },

        "categoryId": categoryID,
        "merchantLocationKey": "home"
    }

    response = requests.post('https://api.ebay.com/sell/inventory/v1/offer', headers=headers, json=data)

    print(response.text)
    offerID = json.loads(response.text)
    offerID = offerID['offerId']
    offerID = str(offerID)
    print(offerID)


def publishOffer():
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json',
    }

    response = requests.post('https://api.ebay.com/sell/inventory/v1/offer/' + offerID + '/publish', headers=headers)
    response = str(response)
    if response == '<Response [200]>':
        print('Success')
        driver.close()
    else:
        print(response)


refresh_token_expire = os.getenv("refresh_token_expire")
refresh_token_expire = datetime.strptime(refresh_token_expire, "%Y-%m-%d %H:%M:%S.%f")

access_token_expire = os.getenv("access_token_expire")
access_token_expire = datetime.strptime(access_token_expire, "%Y-%m-%d %H:%M:%S.%f")

if os.getenv("access_token") == "":
    auth_url += f'?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope=https://api.ebay.com/oauth/api_scope/sell.inventory+https://api.ebay.com/oauth/api_scope'

    print(f'Please visit the following URL and authorize the application:\n{auth_url}')
    get_access_token(client_id, client_secret, redirect_uri)

elif refresh_token_expire <= datetime.now():
    print('Authorization required')
    auth_url += f'?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope=https://api.ebay.com/oauth/api_scope/sell.inventory+https://api.ebay.com/oauth/api_scope'

    print(f'Please visit the following URL and authorize the application:\n{auth_url}')
    get_access_token(client_id, client_secret, redirect_uri)

elif access_token_expire <= datetime.now():
    print('getting new access token')
    get_Refresh_Token()
elif access_token_expire >= datetime.now():
    access_token = os.getenv("access_token")
else:
    print('I believe an error has occurred in retrieving the authentication so I am authenticating again.')
    auth_url += f'?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope=https://api.ebay.com/oauth/api_scope/sell.inventory+https://api.ebay.com/oauth/api_scope'

    print(f'Please visit the following URL and authorize the application:\n{auth_url}')
    get_access_token(client_id, client_secret, redirect_uri)

getCategorySuggestions(access_token)
findRequired(access_token)
list_item(access_token, description1=description1, description2=description2, description3=description3,
          description4=description4, allAspectsJSON=allAspectsJSON)
createOffer()
publishOffer()
