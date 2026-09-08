import os
import json
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
    print("🟢 [INFO] Scraping process initiated...")
    
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
        # পেজ বাই পেজ লুপ (১ থেকে ২০ পেজ)
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
                            
                        detail_url = link_tag['href']
                        if detail_url.rstrip('/') == BASE_URL.rstrip('/') or not detail_url.startswith('http'):
                            continue
                            
                        if any(x in detail_url for x in ['/author/', '/category/', '/tag/', '/page/', 'contact', 'about']):
                            continue
                            
                        if detail_url not in seen_urls:
                            seen_urls.add(detail_url)
                            
                            img_tag = card.find('img')
                            img_url = ""
                            if img_tag:
                                img_url = img_tag.get('data-src') or img_tag.get('src') or img_tag.get('data-lazy-src') or ""
                                
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
                else:
                    # যদি কার্ড না পাওয়া যায়, তবে ডিরেক্ট এংকর ট্যাগ স্ক্যান করবে
                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        if 'mlsbd.co' in href and href.rstrip('/') != BASE_URL.rstrip('/'):
                            if any(x in href for x in ['/author/', '/category/', '/tag/', '/page/', 'contact', 'about']):
                                continue
                            if href not in seen_urls:
                                seen_urls.add(href)
                                img = a.find('img')
                                img_url = img.get('data-src') or img.get('src') if img else ""
                                title = img.get('alt').strip() if (img and img.get('alt') and img.get('alt') != "Featured Image") else clean_title_from_url(href)
                                
                                movies_data.append({
                                    "title": title,
                                    "logo_url": img_url,
                                    "detail_url": href
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
        
        # উন্নত এবং আকর্ষণীয় স্ট্যাটাস মেসেজ (কোনো টাইম/ডেট ছাড়াই)
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
