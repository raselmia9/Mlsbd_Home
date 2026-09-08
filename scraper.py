import os
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import cloudscraper
from bs4 import BeautifulSoup

BASE_URL = "https://mlsbd.co/"
BATCH_SIZE = 50       # প্রতিবারে ৫০টি করে আইটেম প্রসেস করার ব্যাচ
MAX_WORKERS = 15      # কাজের গতি বাড়ানোর জন্য থ্রেড সংখ্যা বাড়িয়ে ১৫ করা হলো

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
    """একটি নির্দিষ্ট কোয়ালিটির লিংক রেজলভ করার হেল্পার ফাংশন"""
    target_links = extract_target_download_links(scraper, q_href)
    if target_links:
        return q_name, target_links
    return None

def scrape_detail_page(scraper, detail_url):
    """প্রতিটি ডিটেইল পেজে প্রবেশ করে এপিসোড বা কোয়ালিটি লিংক দ্রুত সংগ্রহ করবে"""
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
        
        # সিরিজ বা মাল্টি-এপিসোড চেক করা
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
    """প্রতিটি আইটেম আলাদা থ্রেডে প্রসেস করার ফাংশন"""
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'linux', 'desktop': True})
    try:
        print(f"Crawling: {item['title']}")
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
            item_entry["download_links"] = detail_info["download_links"]
            
        return item_entry
    except Exception as e:
        return None

def extract_items_from_soup(soup, seen_urls):
    """সুপ অবজেক্ট থেকে আইটেমগুলো এক্সট্রাক্ট করার হেল্পার ফাংশন"""
    items = []
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
        print(f"Initial items found on homepage: {len(all_items_meta)}")

        # "MORE" বাটনের মাধ্যমে ২০-২৫ বার বা যতদূর লোড করা যায় ডেটা ফেচ করা
        more_button = soup.find(string=lambda t: t and 'more' in t.lower())
        load_more_url = None
        
        if more_button:
            parent_a = more_button.find_parent('a', href=True)
            if parent_a:
                load_more_url = parent_a['href']

        # যদি সরাসরি লিংক না পাওয়া যায়, তবে সাধারণ পেজিনেশন প্যাটার্ন চেক করা
        max_clicks = 25  # আপনার চাওয়া অনুযায়ী ২০-২৫ বার ক্লিক বা রিকোয়েস্ট পাঠানো
        for click_count in range(1, max_clicks + 1):
            if not load_more_url:
                # যদি পেজ ভিত্তিক পেজিনেশন হয় (যেমন /page/2/, /page/3/)
                load_more_url = f"{BASE_URL}page/{click_count + 1}/"
            
            print(f"Fetching more items, batch/page {click_count}...")
            try:
                more_resp = scraper.get(load_more_url, timeout=15)
                if more_resp.status_code != 200:
                    break
                
                more_soup = BeautifulSoup(more_resp.text, 'html.parser')
                new_items = extract_items_from_soup(more_soup, seen_urls)
                
                if not new_items:
                    print("No more items found. Stopping pagination.")
                    break
                    
                all_items_meta.extend(new_items)
                print(f"Total items collected so far: {len(all_items_meta)}")
                
                # পরবর্তী পেজের লিংক খোঁজা
                next_a = more_soup.find('a', class_=lambda x: x and 'next' in x.lower()) or more_soup.find(string=lambda t: t and 'more' in t.lower())
                if next_a and hasattr(next_a, 'find_parent'):
                    p_a = next_a.find_parent('a', href=True)
                    if p_a:
                        load_more_url = p_a['href']
                else:
                    load_more_url = f"{BASE_URL}page/{click_count + 2}/"
                    
                time.sleep(0.5)
            except Exception as e:
                print(f"Pagination finished or error: {e}")
                break

        total_items = len(all_items_meta)
        print(f"Total valid items collected after pagination: {total_items}. Starting multi-threaded processing...")

        movies_data = []
        
        # ব্যাচ বাই ব্যাচ মাল্টিথ্রেডিং প্রসেসিং
        for i in range(0, total_items, BATCH_SIZE):
            batch = all_items_meta[i:i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            print(f"\n--- Processing Batch {batch_num} (Items {i+1} to {min(i + BATCH_SIZE, total_items)}) concurrently ---")
            
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {executor.submit(process_single_item, item): item for item in batch}
                
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        movies_data.append(result)
            
            with open('multilink.json', 'w', encoding='utf-8') as f:
                json.dump(movies_data, f, ensure_ascii=False, indent=4)
            print(f"Batch {batch_num} saved successfully.")

        print(f"\nSuccessfully completed! All {len(movies_data)} items saved to multilink.json")

        status_message = f"SUCCESS: Scraped {len(movies_data)} items with pagination at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(status_message)

    except Exception as e:
        error_msg = f"ERROR: Failed to scrape. Details: {str(e)}"
        print(error_msg)
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(error_msg)

if __name__ == "__main__":
    scrape_mlsbd()
