import os
import json
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

BASE_URL = "https://mlsbd.co/"

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
        
        # এপিসোড বাটন বা টেক্সট খোঁজা
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
            # সাধারণ মুভির জন্য কোয়ালিটি লিংক সংগ্রহ
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
        
        movies_data = []
        seen_urls = set()
        
        cards = soup.select('article, .item, .post-item, .card, .post')
        if not cards:
            cards = soup.find_all('div', class_=lambda x: x and ('post' in x or 'item' in x or 'card' in x))

        print(f"Found {len(cards)} items on homepage. Processing all sequentially...")

        for index, card in enumerate(cards):
            try:
                img_tag = card.find('img')
                img_url = ""
                if img_tag:
                    img_url = img_tag.get('data-src') or img_tag.get('src') or img_tag.get('data-lazy-src') or img_tag.get('srcset')
                
                link_tag = card.find('a', href=True)
                if not link_tag:
                    continue
                    
                detail_url = link_tag['href']
                if detail_url.rstrip('/') == BASE_URL.rstrip('/') or detail_url in seen_urls:
                    continue
                    
                seen_urls.add(detail_url)
                
                # টাইটেল বের করা
                title_tag = card.find(['h2', 'h3', 'h1'])
                if title_tag and title_tag.get_text(strip=True):
                    title = title_tag.get_text(strip=True)
                elif img_tag and img_tag.get('alt') and img_tag.get('alt').strip() != "Featured Image":
                    title = img_tag.get('alt').strip()
                else:
                    title = clean_title_from_url(detail_url)

                print(f"[{index+1}/{len(cards)}] Processing item: {title}")
                
                # ডিটেইল পেজ ক্রল করা
                detail_info = scrape_detail_page(scraper, detail_url)
                
                item_entry = {
                    "title": title,
                    "logo_url": img_url if img_url else "",
                    "detail_url": detail_url,
                    "type": detail_info["type"]
                }
                
                if detail_info["type"] == "series":
                    item_entry["episodes"] = detail_info["episodes"]
                else:
                    item_entry["qualities"] = detail_info["qualities"]

                movies_data.append(item_entry)

            except Exception as e:
                print(f"Error on card {index+1}: {e}")
                continue

        # আউটপুট জেসন ফাইল সেভ করা
        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump(movies_data, f, ensure_ascii=False, indent=4)
        print(f"Successfully saved all {len(movies_data)} items to multilink.json")

        status_message = f"SUCCESS: Scraped {len(movies_data)} items successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(status_message)

    except Exception as e:
        error_msg = f"ERROR: Failed to scrape. Details: {str(e)}"
        print(error_msg)
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(error_msg)
        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    scrape_mlsbd()
