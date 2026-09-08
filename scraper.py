import os
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import cloudscraper
from bs4 import BeautifulSoup

BASE_URL = "https://mlsbd.co/"
BATCH_SIZE = 50       
MAX_WORKERS = 15      

def clean_title_from_url(url):
    """ইউআরএল থেকে সুন্দর একটি টাইটেল তৈরি করার ফাংশন"""
    try:
        path = url.strip('/').split('/')[-1]
        title = path.replace('-', ' ').title()
        return title
    except:
        return "Unknown Title"

def clean_episode_name(text):
    """এপিসোড নাম থেকে অতিরিক্ত অংশ রিমুভ করার ফাংশন"""
    if not text:
        return ""
    cleaned = text.strip()
    if cleaned.lower().startswith("download now"):
        cleaned = cleaned[12:].strip()
    cleaned = cleaned.lstrip("-: ").strip()
    return cleaned if cleaned else text

def is_valid_post_url(url):
    """অথর, ক্যাটাগরি বা অন্যান্য অপ্রয়োজনীয় পেজ বাদ দিয়ে শুধু মুভি/সিরিজের লিংক ফিল্টার করার ফাংশন"""
    url_lower = url.lower()
    invalid_keywords = ['/author/', '/category/', '/tag/', '/genre/', '/page/', 'mlsbd.co/contact', 'mlsbd.co/about']
    for keyword in invalid_keywords:
        if keyword in url_lower:
            return False
    if url_lower.rstrip('/') == BASE_URL.rstrip('/'):
        return False
    return True

def extract_target_download_links(scraper, quality_url):
    """ইন্টারমিডিয়েট পেজ ভিজিট করে নির্দিষ্ট ডোমেইনের লিংকগুলো কালেক্ট করবে"""
    target_links = []
    try:
        response = scraper.get(quality_url, timeout=8)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                if 'hubcloud.foo/video/' in href or 'new2.multicloudlinks.com' in href:
                    if href not in target_links:
                        target_links.append(href)
    except Exception as e:
        pass
    return target_links

def process_single_quality(scraper, q_name, q_href):
    target_links = extract_target_download_links(scraper, q_href)
    if target_links:
        return q_name, target_links
    return None

def scrape_detail_page(scraper, detail_url):
    item_data = {
        "detail_url": detail_url,
        "type": "movie",
        "download_links": {}
    }
    
    try:
        response = scraper.get(detail_url, timeout=12)
        if response.status_code != 200:
            return item_data
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # সিরিজ বা এপিসোড চেক করা
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
                        quality_tasks = []
                        for a_tag in container.find_all('a', href=True):
                            link_text = a_tag.get_text(strip=True).lower()
                            link_href = a_tag['href']
                            
                            if '4k' in link_text or '4k' in link_href:
                                continue
                                
                            for q in ['360p', '480p', '720p', '1080p', 'watch online']:
                                if q in link_text:
                                    quality_tasks.append((q, link_href))
                                    break
                        
                        if quality_tasks:
                            with ThreadPoolExecutor(max_workers=5) as q_executor:
                                future_to_q = {q_executor.submit(process_single_quality, scraper, q_name, q_href): q_name for q_name, q_href in quality_tasks}
                                for future in as_completed(future_to_q):
                                    res = future.result()
                                    if res:
                                        q_name, t_links = res
                                        qualities_map[q_name] = t_links

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
            movie_quality_tasks = []
            for a_tag in soup.find_all('a', href=True):
                text = a_tag.get_text(strip=True).lower()
                href = a_tag['href']
                
                if '4k' in text or '4k' in href:
                    continue
                
                for q in ['360p', '480p', '720p', '1080p', 'watch online']:
                    if q in text:
                        movie_quality_tasks.append((q, href))
                        break
            
            qualities_map = {}
            if movie_quality_tasks:
                with ThreadPoolExecutor(max_workers=5) as q_executor:
                    future_to_q = {q_executor.submit(process_single_quality, scraper, q_name, q_href): q_name for q_name, q_href in movie_quality_tasks}
                    for future in as_completed(future_to_q):
                        res = future.result()
                        if res:
                            q_name, t_links = res
                            qualities_map[q_name] = t_links
            
            item_data["type"] = "movie"
            item_data["download_links"] = qualities_map

        return item_data

    except Exception as e:
        return item_data

def process_single_item(item):
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'linux', 'desktop': True})
    try:
        print(f"Checking & Crawling: {item['title']}")
        detail_info = scrape_detail_page(scraper, item['detail_url'])
        
        # যদি কোনো ডাউনলোড লিংক বা এপিসোড না থাকে, তবে আইটেমটি বাদ দেবো
        if detail_info["type"] == "series":
            if not detail_info["episodes"]:
                print(f"Skipped (No links found): {item['title']}")
                return None
            item_entry = {
                "title": item['title'],
                "logo_url": item['logo_url'],
                "detail_url": item['detail_url'],
                "type": "series",
                "episodes": detail_info["episodes"]
            }
        else:
            if not detail_info["download_links"]:
                print(f"Skipped (No links found): {item['title']}")
                return None
            item_entry = {
                "title": item['title'],
                "logo_url": item['logo_url'],
                "detail_url": item['detail_url'],
                "type": "movie",
                "download_links": detail_info["download_links"]
            }
            
        return item_entry
    except Exception as e:
        return None

def extract_items_from_soup(soup, seen_urls):
    items = []
    cards = soup.find_all(['article', 'div'], class_=lambda x: x and any(c in x.lower() for c in ['item', 'post', 'card', 'box']))
    
    for card in cards:
        link_tag = card.find('a', href=True)
        if not link_tag:
            continue
            
        detail_url = link_tag['href']
        if not detail_url.startswith('http'):
            continue
            
        # ভ্যালিড পোস্ট ইউআরএল চেক করা (অথর বা ক্যাটাগরি বাদ দেওয়া)
        if not is_valid_post_url(detail_url) or detail_url in seen_urls:
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

        items.append({
            "title": title,
            "logo_url": img_url if img_url else "",
            "detail_url": detail_url
        })
    return items

def scrape_mlsbd():
    print(f"Scraping started at: {datetime.now()}")
    
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'linux', 'desktop': True})
    
    try:
        response = scraper.get(BASE_URL, timeout=30)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch homepage, status code: {response.status_code}")
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        seen_urls = set()
        all_items_meta = extract_items_from_soup(soup, seen_urls)
        print(f"Initial valid movie/series items found on homepage: {len(all_items_meta)}")

        # পেজিনেশনের মাধ্যমে আরও আইটেম লোড করা (যেমন ২০-২৫ পেজ)
        max_pages = 25
        for page_num in range(2, max_pages + 2):
            page_url = f"{BASE_URL}page/{page_num}/"
            print(f"Fetching page {page_num}: {page_url}")
            try:
                page_resp = scraper.get(page_url, timeout=15)
                if page_resp.status_code != 200:
                    print("Reached end of pages or page not found.")
                    break
                
                page_soup = BeautifulSoup(page_resp.text, 'html.parser')
                new_items = extract_items_from_soup(page_soup, seen_urls)
                
                if not new_items:
                    print("No more items found on this page.")
                    break
                    
                all_items_meta.extend(new_items)
                print(f"Total valid items collected so far: {len(all_items_meta)}")
                time.sleep(0.3)
            except Exception as e:
                print(f"Pagination finished or error: {e}")
                break

        total_items = len(all_items_meta)
        print(f"\nTotal valid items to process: {total_items}. Starting multi-threaded processing...")

        movies_data = []
        
        for i in range(0, total_items, BATCH_SIZE):
            batch = all_items_meta[i:i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            print(f"\n--- Processing Batch {batch_num} (Items {i+1} to {min(i + BATCH_SIZE, total_items)}) ---")
            
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {executor.submit(process_single_item, item): item for item in batch}
                
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        movies_data.append(result)
            
            with open('multilink.json', 'w', encoding='utf-8') as f:
                json.dump(movies_data, f, ensure_ascii=False, indent=4)
            print(f"Batch {batch_num} saved successfully. Total saved so far: {len(movies_data)}")

        print(f"\nSuccessfully completed! All {len(movies_data)} items saved to multilink.json")

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
