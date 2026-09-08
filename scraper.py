import os
import json
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

# MLSBD URL
BASE_URL = "https://mlsbd.co/"

def scrape_mlsbd():
    print(f"Scraping started at: {datetime.now()}")
    
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
        seen_urls = set() # ডুপ্লিকেট চেক করার জন্য সেট (Set)
        
        # হোমপেজের সমস্ত পোস্ট বা কার্ডগুলো ট্র্যাক করার জন্য আরও ব্রড সিলেক্টর ব্যবহার করা হলো
        # যাতে পেজে থাকা সবগুলো মুভি/পোস্টের কার্ড রিকগনাইজ করা যায়
        cards = soup.select('article, .item, .post-item, .card, .post')
        
        if not cards:
            cards = soup.find_all('div', class_=lambda x: x and ('post' in x or 'item' in x or 'card' in x))

        print(f"Found {len(cards)} potential items/cards on the page.")

        for card in cards:
            try:
                # লোগো বা ছবির লিংক খোঁজা (লেজি লোডিং এট্রিবিউটসহ)
                img_tag = card.find('img')
                img_url = ""
                if img_tag:
                    img_url = (
                        img_tag.get('data-src') or 
                        img_tag.get('src') or 
                        img_tag.get('data-lazy-src') or 
                        img_tag.get('srcset')
                    )
                
                # দ্বিতীয় পেজে যাওয়ার লিংক খোঁজা
                link_tag = card.find('a', href=True)
                detail_url = ""
                title = ""
                
                if link_tag:
                    detail_url = link_tag['href']
                    # সঠিক টাইটেল পাওয়ার জন্য হেডিং বা অ্যাংকরের টেক্সট খোঁজা
                    title_tag = card.find(['h2', 'h3', 'h1', 'span'])
                    if title_tag:
                        title = title_tag.get_text(strip=True)
                    elif link_tag.get_text(strip=True):
                        title = link_tag.get_text(strip=True)

                # যদি লিংক এবং ইমেজ থাকে এবং এটি আগে কখনো সেভ করা না হয়ে থাকে (ডুপ্লিকেট চেক)
                if detail_url and detail_url not in seen_urls:
                    seen_urls.add(detail_url)
                    movies_data.append({
                        "title": title if title else "No Title",
                        "logo_url": img_url if img_url else "",
                        "detail_url": detail_url
                    })
            except Exception as e:
                continue

        # যদি প্রধান সিলেক্টরগুলোতে সব কার্ড কাভার না করে, তবে ফলের পরিধি বাড়াতে অল্টারনেটিভ লুপ
        if len(movies_data) < 5:
            print("Expanding search to all anchor tags with images...")
            for a in soup.find_all('a', href=True):
                img = a.find('img')
                if img:
                    img_url = img.get('data-src') or img.get('src')
                    detail_url = a['href']
                    title = img.get('alt') or a.get_text(strip=True)
                    
                    # ইউনিক লিংক নিশ্চিত করা
                    if detail_url and detail_url not in seen_urls and ('mlsbd.co' in detail_url or detail_url.startswith('/')):
                        seen_urls.add(detail_url)
                        movies_data.append({
                            "title": title if title else "No Title",
                            "logo_url": img_url if img_url else "",
                            "detail_url": detail_url
                        })

        # ১. JSON ফাইল সেভ করা (multilink.json)
        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump(movies_data, f, ensure_ascii=False, indent=4)
        print(f"Successfully saved {len(movies_data)} unique items to multilink.json")

        # ২. স্ট্যাটাস ফাইল তৈরি করা (status.txt)
        status_message = f"SUCCESS: Scraped {len(movies_data)} unique items successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(status_message)
        print(status_message)

    except Exception as e:
        error_msg = f"ERROR: Failed to scrape. Details: {str(e)}"
        print(error_msg)
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(error_msg)
        
        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    scrape_mlsbd()
