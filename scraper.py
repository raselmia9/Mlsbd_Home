import os
import json
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

BASE_URL = "https://mlsbd.co/"
MAX_PAGES = 5  # প্রথমে চেক করার জন্য ৫টি পেজ দিয়ে টেস্ট করতে পারেন

def clean_title_from_url(url):
    try:
        path = url.strip('/').split('/')[-1]
        title = path.replace('-', ' ').title()
        return title
    except:
        return "Unknown Movie"

def scrape_mlsbd():
    print(f"Scraping started at: {datetime.now()}")
    
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'linux',
            'desktop': True
        }
    )
    
    movies_data = []
    seen_urls = set()
    
    try:
        for page_num in range(1, MAX_PAGES + 1):
            if page_num == 1:
                page_url = BASE_URL
            else:
                page_url = f"{BASE_URL}page/{page_num}/"

            print(f"\n--- Fetching Page {page_num}: {page_url} ---")
            
            response = scraper.get(page_url, timeout=30)
            print(f"Status Code: {response.status_code}")
            
            if response.status_code != 200:
                print(f"Failed to fetch. Status: {response.status_code}")
                break
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # ডিবাগ করার জন্য চেক করছি যে পেজে কোনো ট্যাগ পাওয়া যাচ্ছে কিনা
            all_links = soup.find_all('a', href=True)
            print(f"Total links found on page: {len(all_links)}")

            #mlsbd.co এর ভেতরের পোস্ট লিংকগুলো সাধারণত নির্দিষ্ট প্যাটার্নের হয়
            page_items_count = 0
            for a in all_links:
                href = a['href']
                # ফিল্টার: শুধু মুভি বা সিরিজের লিংকগুলো নেওয়ার জন্য
                if 'mlsbd.co' in href and href.rstrip('/') != BASE_URL.rstrip('/'):
                    if any(x in href for x in ['/author/', '/category/', '/tag/', '/page/', 'contact', 'about']):
                        continue
                        
                    if href not in seen_urls:
                        seen_urls.add(href)
                        
                        # টাইটেল এবং ছবি খোঁজার চেষ্টা
                        img = a.find('img')
                        img_url = ""
                        if img:
                            img_url = img.get('data-src') or img.get('src') or ""
                            
                        title = ""
                        if img and img.get('alt') and img.get('alt').strip() != "Featured Image":
                            title = img.get('alt').strip()
                        else:
                            title = clean_title_from_url(href)
                            
                        movies_data.append({
                            "title": title,
                            "logo_url": img_url,
                            "detail_url": href
                        })
                        page_items_count += 1

            print(f"Collected {page_items_count} items from page {page_num}. Total unique items: {len(movies_data)}")

        # JSON ফাইলে সেভ করা
        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump(movies_data, f, ensure_ascii=False, indent=4)
        print(f"\nSuccessfully saved {len(movies_data)} items to multilink.json")

    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    scrape_mlsbd()
