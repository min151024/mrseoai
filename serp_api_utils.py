from serpapi import GoogleSearch
import os
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import requests

load_dotenv()
api_key = os.getenv("SERPAPI_API_KEY")

def get_top_competitor_urls(keyword, num_results=5):
    params = {
        "engine": "google",
        "q": keyword,
        "api_key": os.getenv("SERPAPI_API_KEY"),
        "num": num_results,
        "hl": "ja",  # 日本語で取得
    }

    
    search = GoogleSearch(params)
    results = search.get_dict()
    print("🔍 SerpAPIの生データ:", results)

    urls = []
    for result in results.get("organic_results", []):
        link = result.get("link")
        if link:
            urls.append(link)
    return urls

def get_meta_info_from_url(url):
    try:
        response = requests.get(url, timeout=5)
        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.string if soup.title else ""
        description_tag = soup.find("meta", attrs={"name": "description"})
        description = description_tag["content"] if description_tag else ""
        return {
            "url": url,
            "title": title,
            "description": description
        }
    except Exception as e:
        print(f"⚠️ エラー発生: {url} -> {e}")
        return {
            "url": url,
            "title": "",
            "description": ""
        }