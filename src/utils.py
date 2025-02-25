import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
import requests
import asyncio
import aiohttp
from pathlib import Path
import re


chromeProfilePath = os.path.join(os.getcwd(), "chrome_profile", "scene_profile")
seen_file = os.path.join(os.getcwd(),'.cache','seen_files')
seen_files = []

NTFURL_API = "https://nitroflare.com/api/v2"
NTFURL_KEYINFO = f"{NTFURL_API}/getKeyInfo"
NTFURL_FILEINFO = f"{NTFURL_API}/getFileInfo"
NTFURL_DOWNLOADLINK = f"{NTFURL_API}/getDownloadLink"
NTFURL_FOLDER_INGEST = "http://nitroflare.com/ajax/folder.php"  # A WHA.. WHA...


def write_seen_entry(data):
    with open(seen_file, 'a') as f:
        f.write(f"{data}\n")

async def download_file(url, filepath, title=None):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    with open(filepath, 'wb') as f:
                        while True:
                            chunk = await response.content.read(4096)
                            if not chunk:
                                break
                            f.write(chunk)
                    print(f"Write {url} -> {filepath}")
                    if title:
                        write_seen_entry(title)
                else:
                    print(f"Failed to download {url}, status code: {response.status}")
        except aiohttp.ClientError as e:
            print(f"An error occurred while downloading {url}: {e}")

async def go_download(auri):
    tasks = [download_file(url, name, title) for url, name, title in auri]
    await asyncio.gather(*tasks)

def ensure_seen_file():
    _dir = os.path.dirname(seen_file)
    if not os.path.exists(_dir):
        os.makedirs(_dir)
    if not os.path.exists(seen_file):
        Path(seen_file).touch()
    return seen_file

with open(ensure_seen_file(), 'r') as f:
    seen_files = f.readlines()

def ensure_chrome_profile():
    profile_dir = os.path.dirname(chromeProfilePath)
    if not os.path.exists(profile_dir):
        os.makedirs(profile_dir)
    if not os.path.exists(chromeProfilePath):
        os.makedirs(chromeProfilePath)
    return chromeProfilePath

def chrome_browser_options():
    ensure_chrome_profile()
    options = webdriver.ChromeOptions()
    options.add_argument("--start-minimized")
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument("window-size=200x600")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-translate")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-logging")
    options.add_argument("--disable-autofill")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-animations")
    options.add_argument("--disable-cache")
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])

    prefs = {
        "profile.default_content_setting_values.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2,
    }
    options.add_experimental_option("prefs", prefs)

    if len(chromeProfilePath) > 0:
        initial_path = os.path.dirname(chromeProfilePath)
        profile_dir = os.path.basename(chromeProfilePath)
        options.add_argument('--user-data-dir=' + initial_path)
        options.add_argument("--profile-directory=" + profile_dir)
    else:
        options.add_argument("--incognito")

    return options

def init_browser(chrome_options) -> webdriver.Chrome:
    try:
        options = chrome_options
        service = ChromeService(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize browser: {str(e)}")

def download_files(files, u, p, folder='/data/videos/'):

    def prep_nitroflare(_file_id):
        params = {"files": _file_id}
        if not _file_id in seen_files:
            response = requests.get(url=NTFURL_FILEINFO, params=params)
            if response.status_code == 200:
                j = response.json()
                params = {"user": u, "premiumKey": p, "file": _file_id}
                response = requests.get(url=NTFURL_DOWNLOADLINK, params=params)
                if response.status_code == 200:
                    j = response.json()
                    test = j["result"]["name"]
                    if not 'scan' in test.lower():
                        auri.append((
                            j["result"]["url"],
                            f'''{folder}{test}''',
                            _file_id,
                        ))

    path = Path(folder)
    path.mkdir(parents=True, exist_ok=True)
    fldrdig = r"folder/(?P<USER>\d+)/(?P<ID>[\w=]+)"
    filedig = r"view/([A-Z0-9]+)"
    params = {"user": u, "premiumKey": p}
    
    auri = []
    response = requests.get(url=NTFURL_KEYINFO, params=params)
    if response.status_code == 200:
        j = response.json()
        for uri, _ in files:

            if isinstance(uri, list):
                uri = uri[0]
            # Extract file_id
            match = re.search(filedig, uri)
            if match:
                prep_nitroflare(match.group(1))
                
            elif 'folder' in uri: # we have a folder
                match = re.search(fldrdig, uri)
                if match:
                    data = {
                        "userId": match.group('USER'),
                        "folder": match.group('ID'),
                        "page": 1,
                        "perPage": 10000,
                    }
                    response = requests.post(url=NTFURL_FOLDER_INGEST, data=data)
                    if response.status_code == 200:
                        j = response.json()
                        for link in j['files']:
                            match = re.search(filedig, link['url'])
                            if match:
                                prep_nitroflare(match.group(1))

    if auri:
        asyncio.run(go_download(auri))

