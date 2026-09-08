import os
import json
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

# MLSBD URL
BASE_URL = "https://mlsbd.co/"
MAX_PAGES = 20  # মাল্টি-পেজ ডাটা নেওয়ার জন্য পেজ সংখ্যা ২০ সেট করা হলো

def clean_title_from_url(url):
    """ইউরেনিয়ামের লিংক বা স্লাগ থেকে একটি সুন্দর টাইটেল তৈরি করার ফাংশন"""
    try:
        # যেমন: https://mlsbd.co/malik-2026-bengali-utshob/ -> malik-2026-bengali-utshob
        path = url.strip('/').split('/')[-1]
        # হাইফেন সরিয়ে স্পেস দিয়ে ক্যাপিটালাইজ করা
        title = path.replace('-', ' ').title()
        return title
    except:
        return "Unknown Movie"

def scrape_mlsbd():
    print(f"🟢 [INFO] Scraping process started...")
    
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
        # মাল্টি-পেজ লুপ (১ থেকে ২০ পেজ পর্যন্ত একে একে ডেটা সংগ্রহ করবে)
        for page_num in range(1, MAX_PAGES + 1):
            if page_num == 1:
                page_url = BASE_URL
            else:
                page_url = f"{BASE_URL}page/{page_num}/"

            print(f"📄 [FETCHING] Page {page_num} -> {page_url}")
            
            response = scraper.get(page_url, timeout=30)
            print(f"Response Status Code: {response.status_code}")
            
            if response.status_code != 200:
                print(f"⚠️ [WARNING] Failed to fetch page {page_num}, status code: {response.status_code}")
                continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # হোমপেজের সমস্ত পোস্ট বা কার্ডগুলো খুঁজে বের করা
            cards = soup.select('article, .item, .post-item, .card, .post')
            
            if not cards:
                cards = soup.find_all('div', class_=lambda x: x and ('post' in x or 'item' in x or 'card' in x))

            print(f"Found {len(cards)} potential items/cards on page {page_num}.")

            page_items_count = 0

            for card in cards:
                try:
                    # লোগো বা ছবির লিংক খোঁজা
                    img_tag = card.find('img')
                    img_url = ""
                    if img_tag:
                        img_url = (
                            img_tag.get('data-src') or 
                            img_tag.get('src') or 
                            img_tag.get('data-lazy-src') or 
                            img_tag.get('srcset')
                        )
                    
                    # দ্বিতীয় পেজে যাওয়ার লিংক এবং টাইটেল খোঁজা
                    link_tag = card.find('a', href=True)
                    detail_url = ""
                    title = ""
                    
                    if link_tag:
                        detail_url = link_tag['href']
                        
                        # হোমপেজ বা রুট ইউআরএল হলে তা বাদ দেব
                        if detail_url.rstrip('/') == BASE_URL.rstrip('/'):
                            continue

                        # বিভিন্ন জায়গা থেকে সঠিক টাইটেল খোঁজার চেষ্টা
                        title_tag = card.find(['h2', 'h3', 'h1'])
                        if title_tag and title_tag.get_text(strip=True):
                            title = title_tag.get_text(strip=True)
                        elif link_tag.get_text(strip=True) and len(link_tag.get_text(strip=True)) > 3:
                            title = link_tag.get_text(strip=True)
                        elif img_tag and img_tag.get('alt') and img_tag.get('alt').strip() != "Featured Image":
                            title = img_tag.get('alt').strip()
                        else:
                            # যদি কোথাও আসল নাম না পাওয়া যায়, তবে ইউআরএল/স্লাগ থেকে সুন্দর নাম জেনারেট করব
                            title = clean_title_from_url(detail_url)

                    # ইউনিক এবং ভ্যালিড লিংক চেক করা
                    if detail_url and detail_url.rstrip('/') != BASE_URL.rstrip('/') and detail_url not in seen_urls:
                        seen_urls.add(detail_url)
                        
                        # যদি কোনো কারণে টাইটেল খালি বা 'Featured Image' থেকে যায়, তবে ইউআরএল থেকে জেনারেট করে নেব
                        if not title or title.lower() == "featured image":
                            title = clean_title_from_url(detail_url)

                        movies_data.append({
                            "title": title,
                            "logo_url": img_url if img_url else "",
                            "detail_url": detail_url
                        })
                        page_items_count += 1
                except Exception as e:
                    continue

            # ব্যাকআপ লজিক (যদি কার্ডের মাধ্যমে সব না আসে)
            if page_items_count < 2 and page_num == 1:
                print("Expanding search to all anchor tags with images...")
                for a in soup.find_all('a', href=True):
                    detail_url = a['href']
                    
                    if detail_url.rstrip('/') == BASE_URL.rstrip('/'):
                        continue
                        
                    img = a.find('img')
                    if img:
                        img_url = img.get('data-src') or img.get('src')
                        title = ""
                        if img.get('alt') and img.get('alt').strip() != "Featured Image":
                            title = img.get('alt').strip()
                        elif a.get_text(strip=True) and len(a.get_text(strip=True)) > 3:
                            title = a.get_text(strip=True)
                        else:
                            title = clean_title_from_url(detail_url)
                        
                        if detail_url and detail_url not in seen_urls and ('mlsbd.co' in detail_url or detail_url.startswith('/')):
                            seen_urls.add(detail_url)
                            movies_data.append({
                                "title": title,
                                "logo_url": img_url if img_url else "",
                                "detail_url": detail_url
                            })
                            page_items_count += 1

            print(f"🟢 [SUCCESS] Page {page_num} processed. Collected: {page_items_count} items. Total unique: {len(movies_data)}")
            success_pages += 1

        # ১. JSON ফাইল সেভ করা (multilink.json)
        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump(movies_data, f, ensure_ascii=False, indent=4)
        print(f"\nSuccessfully saved {len(movies_data)} unique items to multilink.json")

        # ২. স্ট্যাটাস ফাইল তৈরি করা (status.txt) - সময় ছাড়া উন্নত সবুজ ডট স্ট্যাটাস
        status_message = f"🟢 SUCCESS: Scraped {len(movies_data)} unique items successfully from {success_pages} pages."
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(status_message)
        print(status_message)

    except Exception as e:
        error_msg = f"❌ ERROR: Failed to scrape. Details: {str(e)}"
        print(error_msg)
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(error_msg)
        
        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    scrape_mlsbd()
