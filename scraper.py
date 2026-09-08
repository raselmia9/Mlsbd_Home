import os
import json
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

# MLSBD URL
BASE_URL = "https://mlsbd.co/"

def scrape_mlsbd():
    print(f"Scraping started at: {datetime.now()}")
    
    # Cloudscraper ব্যবহার করা হচ্ছে যাতে Cloudflare প্রটেকশন থাকলে তা বাইপাস করা যায়
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'linux',
            'desktop': True
        }
    )
    
    try:
        response = scraper.get(BASE_URL, timeout=30)
        print(f"Response Status Code: {response.status_code}")
        
        if response.status_code != 200:
            raise Exception(f"Failed to fetch page, status code: {response.status_code}")
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        movies_data = []
        
        # সাইটের এইচটিএমএল স্ট্রাকচার অনুযায়ী কার্ডগুলো খুঁজে বের করা
        # সাধারণত এ ধরনের সাইটে প্রতিটি পোস্ট বা কার্ড নির্দিষ্ট ক্লাস বা ট্যাগের ভেতরে থাকে। 
        # স্ক্রিনশট অনুযায়ী কার্ডগুলো সাধারণত <article> বা নির্দিষ্ট কোনো class-এর div-এ থাকে। 
        # নিচে একটি জেনারেল সিলেক্টর দেওয়া হলো যা বেশিরভাগ WordPress/Custom সাইটে কাজ করে:
        
        # কার্ড বা পোস্ট এলিমেন্টগুলো খুঁজছি (যেমন: article বা পোস্ট বক্স)
        cards = soup.select('article, .item, .post-item, .card') # আপনি সাইটের স্ট্রাকচার দেখে এটি অ্যাডজাস্ট করতে পারেন
        
        if not cards:
            # যদি জেনেরিক সিলেক্টরে কাজ না করে, তবে ইমেজ বা হেডিং ট্যাগ দিয়ে খোঁজা হবে
            cards = soup.find_all('div', class_=lambda x: x and ('post' in x or 'item' in x or 'card' in x))

        print(Found {len(cards)} potential items/cards.)

        for card in cards:
            try:
                # লোগো বা ছবির লিংক খোঁজা
                img_tag = card.find('img')
                img_url = ""
                if img_tag:
                    # অনেক সময় লেজি লোডিংয়ের কারণে data-src বা src-এ লিংক থাকে
                    img_url = img_tag.get('data-src') or img_tag.get('src') or img_tag.get('data-lazy-src')
                
                # দ্বিতীয় পেজে যাওয়ার লিংক খোঁজা (সাধারণত a ট্যাগের ভেতরে href থাকে)
                link_tag = card.find('a', href=True)
                detail_url = ""
                title = ""
                
                if link_tag:
                    detail_url = link_tag['href']
                    # যদি টাইটেল পাওয়া যায়
                    title_tag = card.find(['h2', 'h3', 'a'])
                    if title_tag:
                        title = title_tag.get_text(strip=True)

                # যদি লিংক এবং ইমেজ পাওয়া যায় তবে লিস্টে যোগ করব
                if detail_url or img_url:
                    movies_data.append({
                        "title": title if title else "No Title",
                        "logo_url": img_url if img_url else "",
                        "detail_url": detail_url if detail_url else ""
                    })
            except Exception as e:
                continue

        # যদি উপরিউক্ত লজিক অনুযায়ী কার্ড সিলেক্ট না হয় (ক্লাস ভিন্ন হওয়ার কারণে), 
        # তবে সমস্ত ইমেজ এবং তাদের সাথে থাকা লিঙ্কগুলো সরাসরি তুলে নেওয়ার একটি অল্টারনেটিভ পদ্ধতি:
        if not movies_data:
            print("Trying alternative extraction method...")
            for a in soup.find_all('a', href=True):
                img = a.find('img')
                if img:
                    img_url = img.get('data-src') or img.get('src')
                    detail_url = a['href']
                    title = img.get('alt') or a.get_text(strip=True)
                    if detail_url and not any(d['detail_url'] == detail_url for d in movies_data):
                        movies_data.append({
                            "title": title,
                            "logo_url": img_url if img_url else "",
                            "detail_url": detail_url
                        })

        # ১. JSON ফাইল সেভ করা (multilink.json)
        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump(movies_data, f, ensure_ascii=False, indent=4)
        print(f"Successfully saved {len(movies_data)} items to multilink.json")

        # ২. স্ট্যাটাস ফাইল তৈরি করা (status.txt)
        status_message = f"SUCCESS: Scraped {len(movies_data)} items successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(status_message)
        print(status_message)

    except Exception as e:
        error_msg = f"ERROR: Failed to scrape. Details: {str(e)}"
        print(error_msg)
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(error_msg)
        
        # খালি বা ডামি জেসন ফাইল রাখা যাতে গিটহব অ্যাকশন ফেইল না করে
        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    scrape_mlsbd()
