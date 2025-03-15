import os
import sys
import requests
import logging
import re
from pathlib import Path
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

import asyncio
import aiohttp

class LMADownloader:

    NTFURL_API = "https://nitroflare.com/api/v2"
    NTFURL_KEYINFO = f"{NTFURL_API}/getKeyInfo"
    NTFURL_FILEINFO = f"{NTFURL_API}/getFileInfo"
    NTFURL_DOWNLOADLINK = f"{NTFURL_API}/getDownloadLink"
    NTFURL_FOLDER_INGEST = "http://nitroflare.com/ajax/folder.php"  # A WHA.. WHA...
    skip = ['DSD', 'DSF', 'ISO', '_16-']

    def __init__(self, **kwargs):
        self.folder_regex = r"folder/(?P<USER>\d+)/(?P<ID>[\w=]+)"
        self.file_id_regex = r"view/([A-Z0-9]+)"
        self.driver = None
        self.seen_files = []
        self.modified_seen_shows = False
        self.chromeProfilePath = os.path.join(os.getcwd(), "chrome_profile", "scene_profile")
        sys.path.append(self.chromeProfilePath)
        self.profile_dir = os.path.basename(self.chromeProfilePath)
        sys.path.append(self.profile_dir)
        self.seen_file = os.path.join(os.getcwd(),'.cache','seen_files')
        self.log_dir = os.path.join(os.getcwd(), "logs")
        self.download_dir = kwargs.get('download_dir', None)
        self.uxs = kwargs.get('uxs', None)
        self.pxs = kwargs.get('pxs', None)
        self.source = kwargs.get('source', None)
        self.filter = kwargs.get('filter', None)
        self.logging_verbose = kwargs.get('logging_verbose', False)
        self._init_logging()
        self.load_seen_files()
        self.init_browser(self.chrome_browser_options())

    def __del__(self):
        self.close()
        logging.info(f'Goodbye from {str(type(self)).replace("<class '", '').replace("'>",'')}')

    def close(self):
        if self.driver:
            try:
                logging.info('Cleanup Chrome')
                self.driver.quit()
                self.driver = None
            except:
                pass

    def setup_request_session(self):
        # Create a Requests session
        self.session = requests.Session()
        # Get cookies from Selenium and add them to Requests session
        for cookie in self.driver.get_cookies():
            self.session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])

    def ensure_log_dir(self):
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def _get_timestamp(self):
        return datetime.now().strftime("%Y_%m_%d_%H_%M_%S")

    def _init_logging(self, **kwargs):
        self.ensure_log_dir()
        self.logger = logging.getLogger(__name__)
        # Set the config/formatter for the handler
        logging.basicConfig(
            level = logging.INFO,
            format = '%(asctime)s:%(levelname)s:%(name)s:%(message)s',
            handlers = [
                logging.FileHandler(os.path.join(self.log_dir, f'autofoo_log_{self._get_timestamp()}.log')),
                logging.StreamHandler(sys.stdout)
            ])
        logging.info(f'Setting log directory at {self.log_dir}')
        if self.logging_verbose:
            self.webdriver_logging = 0
        return True

    def set_params(self, **kwargs):
        self.download_dir = kwargs.get('download_dir', self.download_dir)
        self.uxs = kwargs.get('uxs', self.uxs)
        self.pxs = kwargs.get('pxs', self.pxs)

    def nf_premium(self) -> dict:
        return {"user": self.uxs, "premiumKey": self.pxs}

    def add_seen_show(self, data):
        test = data.upper()
        if not(test in self.seen_files):
            self.seen_files.append(test)
            if not self.modified_seen_shows:
                self.modified_seen_shows = True

    def write_seen_entry(self, data):
        test = data.upper()    
        with open(self.seen_file, 'a') as f:
            f.write(f"\n{test}")
        self.add_seen_show(test)

    def rebuild_seen_files(self):
        #if modified_seen_shows:
        try:
            self.seen_files = sorted(self.seen_files)
            result = "\n".join(self.seen_files)
            with open(self.seen_file, 'w') as f:
                f.write(result)
        except Exception as e:
            logging.error(f'Error writing seen_files: {e}')

    async def download_file(self, url, filepath, title=None):
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
                        logging.info(f"Write {url} -> {filepath}")
                        if title:
                            self.write_seen_entry(title)
                    else:
                        logging.warning(f"Failed to download {url}, status code: {response.status}")
            except aiohttp.ClientError as e:
                logging.error(f"An error occurred while downloading {url}: {e}")

    async def go_download(self, auri):
        tasks = [self.download_file(url, name, title) for url, name, title in auri]
        await asyncio.gather(*tasks)

    def ensure_seen_file(self):
        _dir = os.path.dirname(self.seen_file)
        if not os.path.exists(_dir):
            os.makedirs(_dir)
        if not os.path.exists(self.seen_file):
            Path(self.seen_file).touch()
        return self.seen_file

    def load_seen_files(self):
        logging.info('Loading seen files')
        with open(self.ensure_seen_file(), 'r') as f:
            self.seen_files = sorted(
                set(line.strip() for line \
                    in f if len(line.strip())>0 and line[0] != '#')
            )
        logging.info(f'We have processed {len(self.seen_files)} files prior to this session')
        return self.seen_files

    def ensure_chrome_profile(self):
        profile_dir = os.path.dirname(self.chromeProfilePath)
        if not os.path.exists(self.profile_dir):
            os.makedirs(self.profile_dir)
        if not os.path.exists(self.chromeProfilePath):
            os.makedirs(self.chromeProfilePath)
        return self.chromeProfilePath

    def chrome_browser_options(self):
        self.ensure_chrome_profile()
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
        ##options.add_argument("--disable-logging")
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

        if len(self.chromeProfilePath) > 0:
            initial_path = os.path.dirname(self.chromeProfilePath)
            profile_dir = os.path.basename(self.chromeProfilePath)
            options.add_argument('--user-data-dir=' + initial_path)
            options.add_argument("--profile-directory=" + profile_dir)
        else:
            options.add_argument("--incognito")

        return options

    def init_browser(self, chrome_options) -> webdriver.Chrome:
        try:
            options = chrome_options
            service = ChromeService(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.setup_request_session()
            return self.driver
        except Exception as e:
            logging.critical(f"Failed to initialize browser: {str(e)}")
            raise RuntimeError(f"Failed to initialize browser: {str(e)}")

    def download_files(self, files):

        logging.info(f'Found {len(files)} NF links')

        def prep_nitroflare(_file_id):
            params = {"files": _file_id}
            if not(_file_id.upper() in self.seen_files):
                response = requests.get(url=self.NTFURL_FILEINFO, params=params)
                if response.status_code == 200:
                    j = response.json()
                    params = self.nf_premium() 
                    params['file'] = _file_id
                    response = requests.get(url=self.NTFURL_DOWNLOADLINK, params=params)
                    if response.status_code == 200:
                        j = response.json()
                        test = j["result"]["name"]
                        if not 'scan' in test.lower():
                            auri.append((
                                j["result"]["url"],
                                os.path.join(self.download_dir, test),
                                _file_id,
                            ))
            else:
                logging.warning(f'We have seen {_file_id}')

        path = Path(self.download_dir)
        path.mkdir(parents=True, exist_ok=True)
        
        auri = []
        response = requests.get(url=self.NTFURL_KEYINFO, params=self.nf_premium())
        if response.status_code == 200:
            j = response.json()
            logging.info(' '.join(['user is', j['result']['status'], 
                'remaining:', str(j['result']['trafficLeft']/1024/1024/1024),
                'GiB']))
            
            for uri in files:
                if isinstance(uri, list):
                    uri = uri[0]
                # Extract file_id
                match = re.search(self.file_id_regex, uri)
                if match:
                    prep_nitroflare(match.group(1))
                elif 'folder' in uri:  # we have a folder to process
                    match = re.search(self.folder_regex, uri)
                    if match:
                        found = 0
                        total = 1000
                        page = 1
                        while found < total:
                            data = {
                                "userId": match.group('USER'),
                                "folder": match.group('ID'),
                                "page": page,
                                "perPage": 100,
                            }
                            response = requests.post(url=self.NTFURL_FOLDER_INGEST, data=data)
                            if response.status_code == 200:
                                j = response.json()
                                total = j['total']
                                for link in j['files']:
                                    found += 1
                                    if not '_24' in link['name']:
                                        continue
                                    match = re.search(self.file_id_regex, link['url'])
                                    if match:
                                        prep_nitroflare(match.group(1))
                            page += 1

        if auri:
            asyncio.run(self.go_download(auri))

    def get_nitroflare_links(self, url):
        """Follow a nitro.download link and extract nitroflare.com links."""

        all_links = []
        def collect_links():
            """Collects all valid links from the current page."""
            file_elements = self.driver.find_elements(By.CSS_SELECTOR, "a.file_link")  # Adjust if selector changes
            for file in file_elements:
                file_url = file.get_attribute("href")
                if file_url and \
                    "scan" not in file_url.lower() and \
                    not self.skip_link(file_url):  # Skip scan-related and unwanted links
                    all_links.add(file_url)

        self.driver.get(url)  # selenium waits for the page to fully load

        # Set results per page to maximum (100)
        try:
            per_page_select = self.driver.find_element(By.NAME, "perPage")
            per_page_select.send_keys("100")  # Set perPage to max
            time.sleep(2)  # Allow page reload
        except:
            logging.error("Failed to set perPage to 100. Continuing...")

        while True:
            collect_links()

            # Extract "Displaying n-m of nnn results" text
            try:
                display_text = self.driver.find_element(By.CLASS_NAME, "displaying-text").text
                match = re.search(r"Displaying \d+-\d+ of (\d+) results", display_text)
                if match:
                    total_results = int(match.group(1))  # Extract total results count
                    last_page_check = re.search(r"Displaying \d+-(\d+) of \d+ results", display_text)
                    if last_page_check:
                        last_item_shown = int(last_page_check.group(1))
                        if last_item_shown == total_results:
                            break  # Last page reached
            except:
                logging.error("Could not find results display text. Assuming last page.")
                break  # If text is missing, assume last page

            # Click Next if still on more pages
            try:
                next_button = self.driver.find_element(By.LINK_TEXT, "Next")  # "Next »"
                next_button.click()
                time.sleep(3)  # Allow next page to load
            except:
                break  # No next button found, exit loop

        return all_links

    def skip_link(self, href):
        return any(_sk in href for _sk in self.skip)

    def load_page(self, url):
        
        self.driver.get(url)  # selenium waits for the page to fully load
        download_links = []

        # Locate the <p> element containing "DOWNLOAD FROM"
        try:
            download_section = self.driver.find_element(By.XPATH, '//p[strong[contains(text(), "DOWNLOAD FROM")]]')
            # Find all <a> tags within this section
            links = download_section.find_elements(By.TAG_NAME, 'a')
            for link in links:
                href = link.get_attribute('href')
                if href:
                    if self.skip_link(href):
                        continue
                    download_links.append(href)

        except Exception as e:
            logging.error(f"Error processing {url}: {e}")

        return download_links

    def get_download_links(self):
        
        logging.info(f'Scrape {self.source} for NF links')
        continue_urls = []
        response = self.driver.get(self.source)
        # Find all 'Continue reading' links
        continue_links = self.driver.find_elements(By.CLASS_NAME, 'more-link')
        if self.filter:
            for link in continue_links:
                _ref = link.get_attribute('href')
                if self.filter.lower() in _ref.lower():
                    continue_urls.append(_ref)
        else:
            continue_urls = [link.get_attribute('href') for link in continue_links]

        return continue_urls
