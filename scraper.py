import os
import json
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

def clean_title_from_url(url):
    """ইউআরএল বা স্লাগ থেকে একটি সুন্দর টাইটেল তৈরি করার ফাংশন"""
    try:
        path = url.strip('/').split('/')[-1]
        title = path.replace('-', ' ').title()
        return title
    except:
        return "Unknown Movie"

def scrape_mlsbd():
    print(f"🔵 INFO: Scraping started at: {datetime.now()}")
    
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'linux',
            'desktop': True
        }
    )
    
    movies_data = []
    seen_urls = set()
    
    # পেজ ১ (হোমপেজ) থেকে শুরু করে পেজ ১০ পর্যন্ত অটোমেটিক জেনারেট করা
    urls_to_scrape = ["https://mlsbd.co/"] + [f"https://mlsbd.co/page/{i}/" for i in range(2, 11)]
    
    for base_url in urls_to_scrape:
        print(f"\n🟡 PROGRESS: Scraping URL -> {base_url}")
        try:
            response = scraper.get(base_url, timeout=30)
            print(f"🔵 INFO: Response Status Code: {response.status_code}")
            
            if response.status_code != 200:
                print(f"🟡 WARNING: Skipping {base_url}, status code: {response.status_code}")
                continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # পোস্ট বা কার্ডগুলো খুঁজে বের করা
            cards = soup.select('article, .item, .post-item, .card, .post')
            if not cards:
                cards = soup.find_all('div', class_=lambda x: x and ('post' in x or 'item' in x or 'card' in x))

            print(f"🔵 INFO: Found {len(cards)} potential items/cards on this page.")

            for card in cards:
                try:
                    # ছবির লিংক খোঁজা
                    img_tag = card.find('img')
                    img_url = ""
                    if img_tag:
                        img_url = (
                            img_tag.get('data-src') or 
                            img_tag.get('src') or 
                            img_tag.get('data-lazy-src') or 
                            img_tag.get('srcset')
                        )
                    
                    # ডিটেইল লিংক এবং টাইটেল খোঁজা
                    link_tag = card.find('a', href=True)
                    detail_url = ""
                    title = ""
                    
                    if link_tag:
                        detail_url = link_tag['href']
                        
                        if detail_url.rstrip('/') == base_url.rstrip('/'):
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

                    if detail_url and detail_url not in seen_urls:
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

        except Exception as e:
            print(f"🔴 ERROR: Failed to scrape {base_url}: {str(e)}")

    try:
        # ১. JSON ফাইল সেভ করা (multilink.json)
        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump(movies_data, f, ensure_ascii=False, indent=4)
        
        # ২. উন্নত স্ট্যাটাস ফাইল তৈরি করা (status.txt) - রঙিন ডটসহ
        if len(movies_data) > 0:
            status_message = f"🟢 SUCCESS: Scraped total {len(movies_data)} unique items successfully from pages 1 to 10 at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        else:
            status_message = f"🟡 WARNING: Scraped 0 items. Please check connection or site layout at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(status_message)
        print(f"\n{status_message}")

    except Exception as e:
        error_msg = f"🔴 ERROR: Failed to save data. Details: {str(e)}"
        print(error_msg)
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(error_msg)

if __name__ == "__main__":
    scrape_mlsbd()
