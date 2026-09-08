import os
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import cloudscraper
from bs4 import BeautifulSoup

BASE_URL = "https://mlsbd.co/"
BATCH_SIZE = 100      
MAX_WORKERS = 20      

def clean_title_from_url(url):
    try:
        path = url.strip('/').split('/')[-1]
        title = path.replace('-', ' ').title()
        return title
    except:
        return "Unknown Title"

def clean_episode_name(text):
    if not text:
        return ""
    cleaned = text.strip()
    if cleaned.lower().startswith("download now"):
        cleaned = cleaned[12:].strip()
    cleaned = cleaned.lstrip("-: ").strip()
    return cleaned if cleaned else text

def is_valid_post_url(url):
    url_lower = url.lower()
    invalid_keywords = ['/author/', '/category/', '/tag/', '/genre/', '/page/', 'mlsbd.co/contact', 'mlsbd.co/about', 'wp-content']
    for keyword in invalid_keywords:
        if keyword in url_lower:
            return False
    if url_lower.rstrip('/') == BASE_URL.rstrip('/'):
        return False
    return True

def scrape_detail_page_fast(scraper, detail_url):
    item_data = {
        "detail_url": detail_url,
        "type": "movie",
        "download_links": {}
    }
    
    try:
        response = scraper.get(detail_url, timeout=8)
        if response.status_code != 200:
            return item_data
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        text_nodes = soup.find_all(string=lambda t: t and ('epi' in t.lower() or 'episode' in t.lower()))
        
        seen_episodes = set()
        episodes_list = []
        
        for node in text_nodes:
            parent = node.parent
            raw_ep_text = node.strip()
            
            if len(raw_ep_text) < 40 and ('epi' in raw_ep_text.lower() or 'episode' in raw_ep_text.lower()):
                ep_text = clean_episode_name(raw_ep_text)
                
                if ep_text and ep_text not in seen_episodes:
                    seen_episodes.add(ep_text)
                    
                    qualities_map = {}
                    container = parent.find_parent(['div', 'section', 'p', 'tr', 'li'])
                    if container:
                        for a_tag in container.find_all('a', href=True):
                            link_text = a_tag.get_text(strip=True).lower()
                            link_href = a_tag['href']
                            
                            if '4k' in link_text or '4k' in link_href:
                                continue
                            if '/category/' in link_href:
                                continue
                                
                            for q in ['360p', '480p', '720p', '1080p', 'watch online']:
                                if q in link_text and q not in qualities_map:
                                    qualities_map[q] = link_href
                                    break

                    has_resolution = any(q in qualities_map for q in ['360p', '480p', '720p', '1080p'])
                    if has_resolution and 'watch online' in qualities_map:
                        del qualities_map['watch online']

                    if qualities_map:
                        episodes_list.append({
                            "episode_name": ep_text,
                            "download_links": qualities_map
                        })

        if episodes_list:
            item_data["type"] = "series"
            item_data["episodes"] = episodes_list
            item_data.pop("download_links", None)
        else:
            qualities_map = {}
            for a_tag in soup.find_all('a', href=True):
                text = a_tag.get_text(strip=True).lower()
                href = a_tag['href']
                
                if '4k' in text or '4k' in href:
                    continue
                if '/category/' in href:
                    continue
                
                for q in ['360p', '480p', '720p', '1080p', 'watch online']:
                    if q in text and q not in qualities_map:
                        qualities_map[q] = href
                        break
            
            has_resolution = any(q in qualities_map for q in ['360p', '480p', '720p', '1080p'])
            if has_resolution and 'watch online' in qualities_map:
                del qualities_map['watch online']
            
            item_data["type"] = "movie"
            item_data["download_links"] = qualities_map

        return item_data

    except Exception as e:
        return item_data

def process_single_item(item):
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'linux', 'desktop': True})
    try:
        detail_info = scrape_detail_page_fast(scraper, item['detail_url'])
        
        if detail_info["type"] == "series":
            if not detail_info["episodes"]:
                return None
            item_entry = {
                "title": item['title'],
                "logo_url": item['logo_url'],
                "detail_url": item['detail_url'],
                "date_time": item['date_time'],  # ডেট ও টাইম যুক্ত করা হলো
                "type": "series",
                "episodes": detail_info["episodes"]
            }
        else:
            if not detail_info["download_links"]:
                return None
            item_entry = {
                "title": item['title'],
                "logo_url": item['logo_url'],
                "detail_url": item['detail_url'],
                "date_time": item['date_time'],  # ডেট ও টাইম যুক্ত করা হলো
                "type": "movie",
                "download_links": detail_info["download_links"]
            }
            
        return (item['original_index'], item_entry)
    except Exception as e:
        return None

def extract_items_from_soup(soup, seen_urls, global_index_counter):
    items = []
    cards = soup.find_all(['article', 'div'], class_=lambda x: x and any(c in x.lower() for c in ['item', 'post', 'card', 'box', 'content']))
    
    for card in cards:
        link_tag = card.find('a', href=True)
        if not link_tag:
            continue
            
        detail_url = link_tag['href']
        if not detail_url.startswith('http'):
            continue
            
        if not is_valid_post_url(detail_url) or detail_url in seen_urls:
            continue
            
        # ইমেজ বা লোগো সংগ্রহ
        img_tag = card.find('img')
        img_url = ""
        if img_tag:
            img_url = img_tag.get('data-src') or img_tag.get('src') or img_tag.get('data-lazy-src') or img_tag.get('srcset')
        
        # টাইটেল সংগ্রহ
        title_tag = card.find(['h2', 'h3', 'h1', 'span'], class_=lambda x: x and 'title' in x.lower())
        if not title_tag:
            title_tag = card.find(['h2', 'h3', 'h1'])

        if title_tag and title_tag.get_text(strip=True):
            title = title_tag.get_text(strip=True)
        elif img_tag and img_tag.get('alt') and img_tag.get('alt').strip() != "Featured Image":
            title = img_tag.get('alt').strip()
        else:
            title = clean_title_from_url(detail_url)

        # ডেট এবং টাইম বা পোস্টের সময় সংগ্রহ (যেমন: "24 hours ago" বা নির্দিষ্ট ডেট)
        date_time_str = ""
        # ওয়েবসাইটের কার্ডে সাধারণত time ট্যাগ বা ডেটের ক্লাস থাকে
        time_tag = card.find(['span', 'time', 'div'], class_=lambda x: x and any(c in x.lower() for c in ['date', 'time', 'posted', 'ago']))
        if time_tag:
            date_time_str = time_tag.get_text(strip=True)
        else:
            # বিকল্প হিসেবে পুরো কার্ডের টেক্সট থেকে সময় খোঁজা
            for span in card.find_all(['span', 'p']):
                txt = span.get_text(strip=True)
                if 'ago' in txt.lower() or '202' in txt or 'hour' in txt.lower() or 'day' in txt.lower():
                    date_time_str = txt
                    break

        seen_urls.add(detail_url)
        items.append({
            "original_index": global_index_counter[0],
            "title": title,
            "logo_url": img_url if img_url else "",
            "detail_url": detail_url,
            "date_time": date_time_str
        })
        global_index_counter[0] += 1
        
    return items

def scrape_mlsbd():
    print(f"Scraping started at: {datetime.now()}")
    
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'linux', 'desktop': True})
    
    try:
        seen_urls = set()
        all_items_meta = []
        global_index_counter = [0]  # সিকিয়েন্স বা সিরিয়াল ঠিক রাখার জন্য কাউন্টার

        max_pages = 150
        for page_num in range(1, max_pages + 1):
            if page_num == 1:
                page_url = BASE_URL
            else:
                page_url = f"{BASE_URL}page/{page_num}/"

            print(f"Fetching page {page_num}: {page_url}")
            try:
                response = scraper.get(page_url, timeout=12)
                if response.status_code != 200:
                    print(f"Page {page_num} returned status {response.status_code}.")
                    if page_num > 10:
                        break
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                new_items = extract_items_from_soup(soup, seen_urls, global_index_counter)
                
                if not new_items:
                    print(f"No new items on page {page_num}.")
                    if page_num > 5:
                        break
                else:
                    all_items_meta.extend(new_items)
                    print(f"Total collected items metadata so far: {len(all_items_meta)}")
                
                if len(all_items_meta) >= 1600:
                    break
            except Exception as e:
                print(f"Error on page {page_num}: {str(e)}")
                continue

        total_items = len(all_items_meta)
        print(f"\nTotal items to process: {total_items}. Running multi-threaded execution...")

        processed_results = []
        
        for i in range(0, total_items, BATCH_SIZE):
            batch = all_items_meta[i:i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            print(f"Processing Batch {batch_num}...")
            
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {executor.submit(process_single_item, item): item for item in batch}
                
                for future in as_completed(futures):
                    res = future.result()
                    if res:
                        processed_results.append(res)

        # মূল ওয়েবসাইটের সিরিয়াল (লেটেস্ট থেকে পুরাতন) অনুযায়ী সাজানো
        processed_results.sort(key=lambda x: x[0])
        movies_data = [item[1] for item in processed_results]

        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump(movies_data, f, ensure_ascii=False, indent=4)

        print(f"\nSuccessfully completed! All {len(movies_data)} items saved with correct serial and date_time to multilink.json")

        status_message = f"SUCCESS: Scraped {len(movies_data)} items at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(status_message)

    except Exception as e:
        error_msg = f"ERROR: Failed to scrape. Details: {str(e)}"
        print(error_msg)
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(error_msg)

if __name__ == "__main__":
    scrape_mlsbd()
