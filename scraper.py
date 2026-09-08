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

def scrape_detail_page(scraper, detail_url):
    """প্রতিটি ডিটেইল পেজে প্রবেশ করে এপিসোড বা কোয়ালিটি লিংক সংগ্রহ করবে"""
    item_data = {
        "detail_url": detail_url,
        "type": "movie",
        "qualities": {},
        "episodes": []
    }
    
    try:
        response = scraper.get(detail_url, timeout=30)
        if response.status_code != 200:
            return None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ১. চেক করা পেজটি সিরিজ বা মাল্টি-এপিসোড কি না
        # সাধারণত এপিসোডের বাটনগুলোতে 'Epi', 'Episode', বা 'Season' থাকে
        episode_blocks = []
        
        # পেজের সমস্ত হেডিং বা সেকশন দেখা যাক যেখানে এপিসোড থাকতে পারে
        potential_headers = soup.find_all(['h2', 'h3', 'h4', 'strong', 'a', 'div'], string=lambda t: t and any(k in t.lower() for k in ['epi', 'episode', 'season', 'part']))
        
        # অথবা রেড বাটন বা ডাউনলোড সেকশনগুলো ট্র্যাক করা
        download_headers = soup.find_all(string=lambda t: t and ('download now' in t.lower() or 'epi' in t.lower()))
        
        # যদি একাধিক এপিসোড বাটন বা হেডার পাওয়া যায়
        if len(download_headers) > 1 or any('epi' in h.get_text().lower() for h in soup.find_all(['a', 'h3', 'h4', 'span'], string=True) if h.get_text()):
            item_data["type"] = "series"
            
            # পেজে থাকা প্রতিটি এপিসোডের ব্লক বা সেকশন খোঁজা
            # সাধারণত প্রতিটি এপিসোডের জন্য আলাদা কন্টেইনার বা ডাউনলোড বাটন থাকে
            # আমরা পেজের টেক্সট বা ব্লক অ্যানালাইজ করে এপিসোড আলাদা করব
            
            # একটি স্মার্ট এপ্রোচ: পেজে যতগুলো 'Download Now Epi...' বা অনুরূপ টেক্সট আছে সেগুলোকে ধরে লুপ চালানো
            text_nodes = soup.find_all(string=lambda t: t and ('epi' in t.lower() or 'episode' in t.lower()))
            
            seen_episodes = set()
            for node in text_nodes:
                parent = node.parent
                ep_text = node.strip()
                if len(ep_text) < 30 and ep_text not in seen_episodes:
                    seen_episodes.add(ep_text)
                    
                    # এই এপিসোডের আন্ডারে থাকা লিংকগুলো খোঁজার চেষ্টা
                    ep_links = {}
                    # প্যারেন্টের পরবর্তী এলিমেন্ট বা তার ভেতরের লিংকগুলো স্ক্যান করা
                    container = parent.find_parent(['div', 'section', 'p'])
                    if container:
                        for a_tag in container.find_all('a', href=True):
                            link_text = a_tag.get_text(strip=True).lower()
                            link_href = a_tag['href']
                            
                            # কোয়ালিটি ডিটেকশন
                            for q in ['360p', '480p', '720p', '1080p', '4k', 'watch online']:
                                if q in link_text:
                                    ep_links[q] = link_href
                                    break
                            else:
                                if 'watch' in link_text or 'online' in link_text:
                                    ep_links['watch_online'] = link_href

                    item_data["episodes"].append({
                        "episode_name": ep_text,
                        "qualities": ep_links
                    })
        
        # যদি সিরিজ না হয়ে সাধারণ মুভি হয়
        if item_data["type"] == "movie" or not item_data["episodes"]:
            item_data["type"] = "movie"
            qualities_dict = {}
            
            # পেজের সব ডাউনলোড লিংক স্ক্যান করা
            for a_tag in soup.find_all('a', href=True):
                text = a_tag.get_text(strip=True).lower()
                href = a_tag['href']
                
                # ফ্লেক্সিবল কোয়ালিটি ম্যাচিং (360p থেকে 4K বা অনলাইন ওয়াচ)
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
        return None

def scrape_mlsbd():
    print(f"Phase 2 Scraping started at: {datetime.now()}")
    
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

        print(f"Found {len(cards)} items on homepage. Starting deep crawl...")

        for card in cards:
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

                print(f"Crawling details for: {title}")
                
                # ডিটেইল পেজ থেকে ভেতরের লিংক বা এপিসোড ফেচ করা
                detail_info = scrape_detail_page(scraper, detail_url)
                
                item_entry = {
                    "title": title,
                    "logo_url": img_url if img_url else "",
                    "detail_url": detail_url,
                    "type": detail_info["type"] if detail_info else "movie"
                }
                
                if detail_info and detail_info["type"] == "series":
                    item_entry["episodes"] = detail_info["episodes"]
                else:
                    item_entry["qualities"] = detail_info["qualities"] if detail_info else {}

                movies_data.append(item_entry)

            except Exception as e:
                continue

        # আউটপুট জেসন ফাইল সেভ করা
        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump(movies_data, f, ensure_ascii=False, indent=4)
        print(f"Successfully saved {len(movies_data)} items with deep details to multilink.json")

        # স্ট্যাটাস ফাইল তৈরি করা
        status_message = f"SUCCESS: Phase 2 completed. Scraped {len(movies_data)} items at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(status_message)

    except Exception as e:
        error_msg = f"ERROR: Phase 2 failed. Details: {str(e)}"
        print(error_msg)
        with open('status.txt', 'w', encoding='utf-8') as f:
            f.write(error_msg)
        with open('multilink.json', 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    scrape_mlsbd()
