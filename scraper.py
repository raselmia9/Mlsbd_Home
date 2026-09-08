import os
import json
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

# MLSBD URL
BASE_URL = "https://mlsbd.co/"
MAX_PAGES = 300  # আপনার চাহিদা অনুযায়ী ৩০০ পেজ সেট করা হলো

# ১৮+ বা অ্যাডাল্ট কন্টেন্ট চেনার জন্য কিওয়ার্ড লিস্ট
ADULT_KEYWORDS = ['18+', '18-plus', '18 plus', '-18-', 'adult', 'erotic', 'ullu', 'kooku', 'primeshots', 'xprime', 'hot web series']

def is_18_plus(title, url):
    """টাইটেল বা ইউআরএল-এর মধ্যে ১৮+ কিওয়ার্ড আছে কিনা তা চেক করার ফাংশন"""
    text_to_check = f"{title} {url}".lower()
    for keyword in ADULT_KEYWORDS:
        if keyword in text_to_check:
            return True
    return False

def clean_title_from_url(url):
    """ইউরেনিয়ামের লিংক বা স্লাগ থেকে একটি সুন্দর টাইটেল তৈরি করার ফাংশন"""
    try:
        path = url.strip('/').split('/')[-1]
        title = path.replace('-', ' ').title()
        return title
    except:
        return "Unknown Movie"

def extract_date_from_card(card):
    """কার্ড থেকে পোস্টের ডেট বা সময় খুঁজে বের করার ফাংশন"""
    date_str = ""
    # ওয়ার্ডপ্রেসের সাধারণত time ট্যাগ বা ডেট ক্লাস থাকে
    time_tag = card.find(['time', 'span', 'div'], class_=lambda x: x and any(c in x.lower() for c in ['date', 'time', 'posted', 'ago']))
    if time_tag:
        date_str = time_tag.get('datetime') or time_tag.get_text(strip=True)
    else:
        # বিকল্প হিসেবে কার্ডের ভেতর কোনো টেক্সট বা টাইম প্যাটার্ন খোঁজা
        for tag in card.find_all(['span', 'p', 'div']):
            txt = tag.get_text(strip=True)
            if 'ago' in txt.lower() or '202' in txt or 'hour' in txt.lower() or 'day' in txt.lower() or 'min' in txt.lower():
                date_str = txt
                break
    return date_str

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
        # ৩০০ পেজ পর্যন্ত লুপ চালিয়ে ডেটা সংগ্রহ করা
        for page_num in range(1, MAX_PAGES + 1):
            if page_num == 1:
                page_url = BASE_URL
            else:
                page_url = f"{BASE_URL}page/{page_num}/"

            print(f"Fetching page {page_num}: {page_url}")
            
            response = scraper.get(page_url, timeout=20)
            if response.status_code != 200:
                print(f"Page {page_num} returned status {response.status_code}. Stopping pagination.")
                break
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            cards = soup.select('article, .item, .post-item, .card, .post')
            if not cards:
                cards = soup.find_all('div', class_=lambda x: x and ('post' in x or 'item' in x or 'card' in x))

            if not cards:
                print(f"No cards found on page {page_num}. Ending scrape.")
                break

            page_items_count = 0

            for card in cards:
                try:
                    img_tag = card.find('img')
                    img_url = ""
                    if img_tag:
                        img_url = (
                            img_tag.get('data-src') or 
                            img_tag.get('src') or 
                            img_tag.get('data-lazy-src') or 
                            img_tag.get('srcset')
                        )
                    
                    link_tag = card.find('a', href=True)
                    detail_url = ""
                    title = ""
                    
                    if link_tag:
                        detail_url = link_tag['href']
                        
                        if detail_url.rstrip('/') == BASE_URL.rstrip('/'):
                            continue

                        title_tag = card.find(['h2', 'h3', 'h1'])
                        if title_tag and title_tag.get_text(strip=True):
                            title = title_tag.get_text(strip=True)
                        elif link_tag.get_text(strip=True) and len(link_tag.get_text(strip=True)) > 3:
                            title = link_tag.get_text(strip=True)
                        elif img_tag and img_tag.get('alt') and img_tag.get('alt').strip() != "Featured Image":
                            title = img_tag.get('alt').strip()
                        else:
                            title = clean_title_from_url(detail_url)

                    # ১৮+ বা অ্যাডাল্ট কন্টেন্ট ফিল্টার করা
                    if is_18_plus(title, detail_url):
                        continue

                    if detail_url and detail_url.rstrip('/') != BASE_URL.rstrip('/') and detail_url not in seen_urls:
                        seen_urls.add(detail_url)
                        
                        if not title or title.lower() == "featured image":
                            title = clean_title_from_url(detail_url)

                        # কার্ড থেকে ডেট সংগ্রহ করা
                        post_date = extract_date_from_card(card)

                        movies_data.append({
                            "title": title,
                            "logo_url": img_url if img_url else "",
                            "detail_url": detail_url,
                            "date": post_date  # নতুন যুক্ত করা ডেট ফিল্ড
                        })
                        page_items_count += 1
                except Exception as e:
                    continue
            
            print(f"Collected {page_items_count} items from page {page_num}. Total items: {len(movies_data)}")

        # ১. JSON ফাইল সেভ করা (multilink.json)
        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump(movies_data, f, ensure_ascii=False, indent=4)
        print(f"Successfully saved {len(movies_data)} unique items to multilink.json")

        # ২. স্ট্যাটাস ফাইল তৈরি করা (status.txt)
        status_message = f"SUCCESS: Scraped {len(movies_data)} unique items successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(status_message)

    except Exception as e:
        error_msg = f"ERROR: Failed to scrape. Details: {str(e)}"
        print(error_msg)
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(error_msg)
        
        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    scrape_mlsbd()
