import os
import json
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

# এখানে আপনি যত খুশি লিংক একসাথে যুক্ত করতে পারবেন (Multi-Link Support)
URLS_TO_SCRAPE = [
    "https://mlsbd.co/",
    "https://mlsbd.co/page/2/",
    # চাইলে আরও ক্যাটাগরি বা পেজের লিংক এখানে যোগ করতে পারেন
    # "https://mlsbd.co/category/action/"
]

def clean_title_from_url(url):
    """ইউআরএল বা স্লাগ থেকে একটি সুন্দর টাইটেল তৈরি করার ফাংশন"""
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
    
    # মাল্টি-লিংক লুপ (প্রতিটি লিংকের জন্য আলাদাভাবে কাজ করবে)
    for base_url in URLS_TO_SCRAPE:
        print(f"\nScraping URL: {base_url}")
        try:
            response = scraper.get(base_url, timeout=30)
            print(f"Response Status Code for {base_url}: {response.status_code}")
            
            if response.status_code != 200:
                print(f"Skipping {base_url}, status code: {response.status_code}")
                continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # হোমপেজ বা পেজের সমস্ত পোস্ট বা কার্ডগুলো খুঁজে বের করা
            cards = soup.select('article, .item, .post-item, .card, .post')
            
            if not cards:
                cards = soup.find_all('div', class_=lambda x: x and ('post' in x or 'item' in x or 'card' in x))

            print(f"Found {len(cards)} potential items/cards on {base_url}")

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
                    
                    # ডিটেইল পেজে যাওয়ার লিংক এবং টাইটেল খোঁজা
                    link_tag = card.find('a', href=True)
                    detail_url = ""
                    title = ""
                    
                    if link_tag:
                        detail_url = link_tag['href']
                        
                        # রুট ইউআরএল হলে তা বাদ দেব
                        if detail_url.rstrip('/') == base_url.rstrip('/'):
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
                            title = clean_title_from_url(detail_url)

                    # ইউনিক এবং ভ্যালিড লিংক চেক করা
                    if detail_url and detail_url.rstrip('/') != base_url.rstrip('/') and detail_url not in seen_urls:
                        seen_urls.add(detail_url)
                        
                        if not title or title.lower() == "featured image":
                            title = clean_title_from_url(detail_url)

                        movies_data.append({
                            "title": title,
                            "logo_url": img_url if img_url else "",
                            "detail_url": detail_url
                        })
                except Exception as e:
                    continue

            # ব্যাকআপ লজিক (যদি কার্ডের মাধ্যমে সব না আসে)
            if len(cards) == 0:
                print(f"Expanding search for {base_url}...")
                for a in soup.find_all('a', href=True):
                    detail_url = a['href']
                    
                    if detail_url.rstrip('/') == base_url.rstrip('/'):
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
                            
        except Exception as e:
            print(f"Error scraping {base_url}: {str(e)}")

    try:
        # ১. JSON ফাইল সেভ করা (multilink.json)
        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump(movies_data, f, ensure_ascii=False, indent=4)
        print(f"\nSuccessfully saved total {len(movies_data)} unique items to multilink.json")

        # ২. স্ট্যাটাস ফাইল তৈরি করা (status.txt)
        status_message = f"SUCCESS: Scraped {len(movies_data)} unique items successfully from multiple links at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(status_message)
        print(status_message)

    except Exception as e:
        error_msg = f"ERROR: Failed to save data. Details: {str(e)}"
        print(error_msg)
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(error_msg)

if __name__ == "__main__":
    scrape_mlsbd()
