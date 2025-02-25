import sys
import os
import re
from datetime import datetime, timedelta, timezone
from src.utils import chrome_browser_options, init_browser, download_files
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
import time

sys.path.append(str(Path(__file__).resolve().parent / 'src'))

upo = os.getenv("NTFLR_USERNAME")
if not upo:
    print("NTFLR_USERNAME not set")
    sys.exit(1)

ppo = os.getenv("NTFLR_PREMIUM")

chrome_options = chrome_browser_options()
driver = init_browser(chrome_options)

_url = 'https://losslessma.net/category/reggae-ska/'


def get_nitroflare_links(url):
    """Follow a nitro.download link and extract nitroflare.com links."""

    all_links = set()
    def collect_links():
        """Collects all valid links from the current page."""
        file_elements = driver.find_elements(By.CSS_SELECTOR, "a.file_link")  # Adjust if selector changes
        for file in file_elements:
            file_url = file.get_attribute("href")
            if file_url and "scan" not in file_url.lower():  # Skip scan-related links
                all_links.add(file_url)

    driver.get(url)
    time.sleep(3)  # Wait for the page to load

    # Set results per page to maximum (100)
    try:
        per_page_select = driver.find_element(By.NAME, "perPage")
        per_page_select.send_keys("100")  # Set perPage to max
        time.sleep(2)  # Allow page reload
    except:
        print("Failed to set perPage to 100. Continuing...")

    while True:
        collect_links()

        # Extract "Displaying n-m of nnn results" text
        try:
            display_text = driver.find_element(By.CLASS_NAME, "displaying-text").text
            match = re.search(r"Displaying \d+-\d+ of (\d+) results", display_text)
            if match:
                total_results = int(match.group(1))  # Extract total results count
                last_page_check = re.search(r"Displaying \d+-(\d+) of \d+ results", display_text)
                if last_page_check:
                    last_item_shown = int(last_page_check.group(1))
                    if last_item_shown == total_results:
                        break  # Last page reached
        except:
            print("Could not find results display text. Assuming last page.")
            break  # If text is missing, assume last page

        # Click Next if still on more pages
        try:
            next_button = driver.find_element(By.LINK_TEXT, "Next")  # "Next »"
            next_button.click()
            time.sleep(3)  # Allow next page to load
        except:
            break  # No next button found, exit loop

    return all_links

def load_page(url):
    
    skip = ('DSD', 'DSF', 'ISO', '_16-')
    driver.get(url)
    time.sleep(1)  # Wait for the page to load
    download_links = []

    # Locate the <p> element containing "DOWNLOAD FROM"
    try:
        download_section = driver.find_element(By.XPATH, '//p[strong[contains(text(), "DOWNLOAD FROM")]]')
        # Find all <a> tags within this section
        links = download_section.find_elements(By.TAG_NAME, 'a')
        for link in links:
            href = link.get_attribute('href')
            if href:
                if any(_sk in href for _sk in skip):
                    continue
                if 1==2 and 'nitro.download' in href:
                    nitroflare_links = get_nitroflare_links(href)
                    download_links.extend(nitroflare_links)
                else:
                    download_links.append((href, None))

    except Exception as e:
        print(f"Error processing {url}: {e}")

    return download_links

def get_download_links(url):

    driver.get(url)
    time.sleep(2)  # Wait for the page to load

    # Find all 'Continue reading' links
    continue_links = driver.find_elements(By.CLASS_NAME, 'more-link')
    continue_urls = [link.get_attribute('href') for link in continue_links]

    return continue_urls


follow = []
links = get_download_links(_url)

# Print all collected download links
for link in links:
    follow.append(load_page(link))

# really need to add the links to a download stream
# the download stream would own all downloads and
# monitor and meter bandwidth
print('go nit-ro')
for link in follow:
    download_files(link, upo, ppo, folder='/media/stuart/one/pre/')

# Close the browser
driver.quit()

