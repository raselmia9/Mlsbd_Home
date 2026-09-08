import os
import json
import time
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

BASE_URL = "https://mlsbd.co/"
BATCH_SIZE = 50  # প্রতিবারে ৫০টি করে আইটেম প্রসেস করার লিমিট

def clean_title_from_url(url):
    """ইউআরএল থেকে সুন্দর একটি টাইটেল তৈরি করার ফাংশন"""
    try:
        path = url.strip('/').split('/')[-1]
        title = path.replace('-', ' ').title()
        return title
    except:
        return "Unknown Title"

def clean_episode_name(text):
    """এপিসোড নাম থেকে 'Download Now' বা অতিরিক্ত অংশ রিমুভ করার ফাংশন"""
    if not text:
        return ""
    cleaned = text.strip()
    if cleaned.lower().startswith("download now"):
        cleaned = cleaned[12:].strip()
    cleaned = cleaned.lstrip("-: ").strip()
    return cleaned if cleaned else text

def scrape_detail_page(scraper, detail_url):
    """প্রতিটি ডিটেইল পেজে প্রবেশ করে এপিসোড বা কোয়ালিটি লিংক সংগ্রহ করবে"""
    item_data = {
        "detail_url": detail_url,
        "type": "movie",
        "qualities": {},
        "episodes": []
    }
    
    try:
        response = scraper.get(detail_url, timeout=15)
        if response.status_code != 200:
            return item_data
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # এপিসোড বা বাটনগুলো খোঁজা
        text_nodes = soup.find_all(string=lambda t: t and ('epi' in t.lower() or 'episode' in t.lower()))
        
        seen_episodes = set()
        for node in text_nodes:
            parent = node.parent
            raw_ep_text = node.strip()
            
            if len(raw_ep_text) < 40 and ('epi' in raw_ep_text.lower() or 'episode' in raw_ep_text.lower()):
                ep_text = clean_episode_name(raw_ep_text)
                
                if ep_text and ep_text not in seen_episodes:
                    seen_episodes.add(ep_text)
                    
                    ep_links = {}
                    container = parent.find_parent(['div', 'section', 'p', 'tr', 'li'])
                    if container:
                        for a_tag in container.find_all('a', href=True):
                            link_text = a_tag.get_text(strip=True).lower()
                            link_href = a_tag['href']
                            
                            for q in ['360p', '480p', '720p', '1080p', '4k', 'watch online']:
                                if q in link_text:
                                    ep_links[q] = link_href
                                    break
                            else:
                                if 'watch' in link_text or 'online' in link_text:
                                    ep_links['watch_online'] = link_href

                    if ep_links:
                        item_data["episodes"].append({
                            "episode_name": ep_text,
                            "qualities": ep_links
                        })

        if item_data["episodes"]:
            item_data["type"] = "series"
        else:
            qualities_dict = {}
            for a_tag in soup.find_all('a', href=True):
                text = a_tag.get_text(strip=True).lower()
                href = a_tag['href']
                
                for q in ['360p', '480p', '720p', '1080p', '4k', 'watch online']:
                    if q in text:
                        qualities_dict[q] = href
                        break
                else:
                    if 'watch' in text or 'online' in text:
                        qualities_dict['watch_online'] = href
            
            item_data["qualities"] = qualities_dict

        return item_data

    except Exception as e:
        print(f"Error scraping detail page {detail_url}: {e}")
        return item_data

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
        if response.status_code != 200:
            raise Exception(f"Failed to fetch homepage, status code: {response.status_code}")
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        all_items_meta = []
        seen_urls = set()
        
        cards = soup.find_all(['article', 'div'], class_=lambda x: x and any(c in x.lower() for c in ['item', 'post', 'card', 'box']))
        
        for card in cards:
            link_tag = card.find('a', href=True)
            if not link_tag:
                continue
                
            detail_url = link_tag['href']
            if not detail_url.startswith('http'):
                continue
                
            if detail_url.rstrip('/') == BASE_URL.rstrip('/') or detail_url in seen_urls:
                continue
                
            seen_urls.add(detail_url)
            
            img_tag = card.find('img')
            img_url = ""
            if img_tag:
                img_url = img_tag.get('data-src') or img_tag.get('src') or img_tag.get('data-lazy-src') or img_tag.get('srcset')
            
            title_tag = card.find(['h2', 'h3', 'h1', 'span'], class_=lambda x: x and 'title' in x.lower())
            if not title_tag:
                title_tag = card.find(['h2', 'h3', 'h1'])

            if title_tag and title_tag.get_text(strip=True):
                title = title_tag.get_text(strip=True)
            elif img_tag and img_tag.get('alt') and img_tag.get('alt').strip() != "Featured Image":
                title = img_tag.get('alt').strip()
            else:
                title = clean_title_from_url(detail_url)

            all_items_meta.append({
                "title": title,
                "logo_url": img_url if img_url else "",
                "detail_url": detail_url,
                "card": card
            })

        total_items = len(all_items_meta)
        print(f"Total valid items found: {total_items}. Processing in batches of {BATCH_SIZE}...")

        movies_data = []
        
        # ব্যাচ বাই ব্যাচ লুপ চালিয়ে ডেটা কালেক্ট করা (যতক্ষণ না সব শেষ হয়)
        for i in range(0, total_items, BATCH_SIZE):
            batch = all_items_meta[i:i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            print(f"\n--- Processing Batch {batch_num} (Items {i+1} to {min(i + BATCH_SIZE, total_items)}) ---")
            
            for index, item in enumerate(batch, start=i+1):
                try:
                    print(f"[{index}/{total_items}] Crawling: {item['title']}")
                    detail_info = scrape_detail_page(scraper, item['detail_url'])
                    
                    item_entry = {
                        "title": item['title'],
                        "logo_url": item['logo_url'],
                        "detail_url": item['detail_url'],
                        "type": detail_info["type"]
                    }
                    
                    if detail_info["type"] == "series":
                        item_entry["episodes"] = detail_info["episodes"]
                    else:
                        item_entry["qualities"] = detail_info["qualities"]

                    movies_data.append(item_entry)
                    time.sleep(0.5) # সার্ভারের সুরক্ষার জন্য ছোট বিরতি
                except Exception as e:
                    print(f"Error on item {index}: {e}")
                    continue
            
            # প্রতি ব্যাচ শেষে অটো সেভ করা, যাতে ডেটা লস না হয়
            with open('multilink.json', 'w', encoding='utf-8') as f:
                json.dump(movies_data, f, ensure_ascii=False, indent=4)
            print(f"Batch {batch_num} saved successfully.")

        print(f"\nSuccessfully completed! All {len(movies_data)} items saved to multilink.json")

        status_message = f"SUCCESS: Scraped {len(movies_data)} items in batches successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(status_message)

    except Exception as e:
        error_msg = f"ERROR: Failed to scrape. Details: {str(e)}"
        print(error_msg)
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(error_msg)

if __name__ == "__main__":
    scrape_mlsbd()
