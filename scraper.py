import os
import json
from urllib.parse import urljoin
import cloudscraper
from bs4 import BeautifulSoup

BASE_URL = "https://mlsbd.co/"
MAX_PAGES = 20  # ২০টি পেজ থেকে ডেটা নেওয়ার জন্য

def clean_title_from_url(url):
    try:
        path = url.strip('/').split('/')[-1]
        title = path.replace('-', ' ').title()
        return title
    except:
        return "Unknown Movie"

def scrape_mlsbd():
    print("🟢 [INFO] Scraping process initiated properly...")
    
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'linux',
            'desktop': True
        }
    )
    
    movies_data = []
    seen_urls = set()
    success_pages = 0
    
    try:
        for page_num in range(1, MAX_PAGES + 1):
            if page_num == 1:
                page_url = BASE_URL
            else:
                page_url = f"{BASE_URL}page/{page_num}/"

            print(f"📄 [FETCHING] Page {page_num} -> {page_url}")
            
            try:
                response = scraper.get(page_url, timeout=30)
                if response.status_code != 200:
                    print(f"⚠️ [WARNING] Page {page_num} returned status code {response.status_code}. Skipping...")
                    continue
                    
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # কার্ড বা পোস্টগুলো খোঁজা
                cards = soup.select('article, .item, .post-item, .card, .post')
                if not cards:
                    cards = soup.find_all('div', class_=lambda x: x and ('post' in x or 'item' in x or 'card' in x))

                page_items_count = 0

                if cards:
                    for card in cards:
                        link_tag = card.find('a', href=True)
                        if not link_tag:
                            continue
                            
                        # রিলেটিভ লিংকগুলোকে পারফেক্ট অ্যাবসোলিউট লিংকে রূপান্তর করা
                        detail_url = urljoin(BASE_URL, link_tag['href'])
                        
                        if detail_url.rstrip('/') == BASE_URL.rstrip('/'):
                            continue
                            
                        if any(x in detail_url for x in ['/author/', '/category/', '/tag/', '/page/', 'contact', 'about']):
                            continue
                            
                        if detail_url not in seen_urls:
                            seen_urls.add(detail_url)
                            
                            img_tag = card.find('img')
                            img_url = ""
                            if img_tag:
                                img_url = img_tag.get('data-src') or img_tag.get('src') or img_tag.get('data-lazy-src') or ""
                                if img_url and not img_url.startswith('http'):
                                    img_url = urljoin(BASE_URL, img_url)
                                
                            title_tag = card.find(['h2', 'h3', 'h1'])
                            if title_tag and title_tag.get_text(strip=True):
                                title = title_tag.get_text(strip=True)
                            elif img_tag and img_tag.get('alt') and img_tag.get('alt').strip() != "Featured Image":
                                title = img_tag.get('alt').strip()
                            else:
                                title = clean_title_from_url(detail_url)

                            movies_data.append({
                                "title": title,
                                "logo_url": img_url,
                                "detail_url": detail_url
                            })
                            page_items_count += 1

                print(f"🟢 [SUCCESS] Page {page_num} processed. Items found: {page_items_count} | Total so far: {len(movies_data)}")
                success_pages += 1

            except Exception as page_err:
                print(f"⚠️ [ERROR] Failed on page {page_num}: {str(page_err)}")
                continue

        # সমস্ত পেজের ডেটা একসাথে multilink.json এ সেভ করা
        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump(movies_data, f, ensure_ascii=False, indent=4)
        
        status_message = f"🟢 SUCCESS: Successfully scraped {len(movies_data)} items from {success_pages} pages."
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(status_message)
            
        print(f"\n✨ {status_message}")

    except Exception as e:
        error_msg = f"❌ ERROR: Process failed completely. Details: {str(e)}"
        print(error_msg)
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(error_msg)
        
        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    scrape_mlsbd()
