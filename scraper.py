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

def extract_target_download_links(scraper, quality_url):
    """ইন্টারমিডিয়েট পেজ ভিজিট করে নির্দিষ্ট ডোমেইনের লিংকগুলো কালেক্ট করবে"""
    target_links = []
    try:
        response = scraper.get(quality_url, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                # কাঙ্ক্ষিত দুটি ডোমেইন ফিল্টার করা
                if 'hubcloud.foo/video/' in href or 'new2.multicloudlinks.com' in href:
                    if href not in target_links:
                        target_links.append(href)
    except Exception as e:
        print(f"Error resolving link {quality_url}: {e}")
    return target_links

def scrape_detail_page(scraper, detail_url):
    """প্রতিটি ডিটেইল পেজে প্রবেশ করে এপিসোড বা কোয়ালিটি লিংক সংগ্রহ ও প্রসেস করবে"""
    item_data = {
        "detail_url": detail_url,
        "type": "movie",
        "download_links": {}
    }
    
    try:
        response = scraper.get(detail_url, timeout=15)
        if response.status_code != 200:
            return item_data
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ১. সিরিজ বা মাল্টি-এপিসোড চেক করা
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
                            
                            # 4K সম্পূর্ণ বাদ দেওয়া এবং অন্যান্য কোয়ালিটি ট্র্যাক করা
                            if '4k' in link_text or '4k' in link_href:
                                continue
                                
                            for q in ['360p', '480p', '720p', '1080p', 'watch online']:
                                if q in link_text:
                                    # রিডাইরেক্ট লিংক থেকে টার্গেট লিংকগুলো বের করা
                                    target_links = extract_target_download_links(scraper, link_href)
                                    if target_links:
                                        qualities_map[q] = target_links
                                    break

                    if qualities_map:
                        episodes_list.append({
                            "episode_name": ep_text,
                            "download_links": qualities_map
                        })

        if episodes_list:
            item_data["type"] = "series"
            item_data["episodes"] = episodes_list
            # সিরিজ হলে রুট লেভেলের download_links দরকার নেই
            item_data.pop("download_links", None)
        else:
            # মুভির ক্ষেত্রে কোয়ালিটি লিংক প্রসেস করা
            qualities_map = {}
            for a_tag in soup.find_all('a', href=True):
                text = a_tag.get_text(strip=True).lower()
                href = a_tag['href']
                
                if '4k' in text or '4k' in href:
                    continue
                
                for q in ['360p', '480p', '720p', '1080p', 'watch online']:
                    if q in text:
                        target_links = extract_target_download_links(scraper, href)
                        if target_links:
                            qualities_map[q] = target_links
                        break
            
            item_data["type"] = "movie"
            item_data["download_links"] = qualities_map

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
                "detail_url": detail_url
            })

        total_items = len(all_items_meta)
        print(f"Total valid items found: {total_items}. Processing in batches of {BATCH_SIZE}...")

        movies_data = []
        
        for i in range(0, total_items, BATCH_SIZE):
            batch = all_items_meta[i:i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            print(f"\n--- Processing Batch {batch_num} (Items {i+1} to {min(i + BATCH_SIZE, total_items)}) ---")
            
            for index, item in enumerate(batch, start=i+1):
                try:
                    print(f"[{index}/{total_items}] Crawling & Resolving Links: {item['title']}")
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

                    movies_data.append(item_entry)
                    time.sleep(0.5)
                except Exception as e:
                    print(f"Error on item {index}: {e}")
                    continue
            
            with open('multilink.json', 'w', encoding='utf-8') as f:
                json.dump(movies_data, f, ensure_ascii=False, indent=4)
            print(f"Batch {batch_num} saved successfully.")

        print(f"\nSuccessfully completed! All {len(movies_data)} items saved to multilink.json")

        status_message = f"SUCCESS: Phase 3 completed. Scraped {len(movies_data)} items at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(status_message)

    except Exception as e:
        error_msg = f"ERROR: Failed to scrape. Details: {str(e)}"
        print(error_msg)
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(error_msg)

if __name__ == "__main__":
    scrape_mlsbd()
