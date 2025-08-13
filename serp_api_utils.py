from serpapi import GoogleSearch
import os
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import requests

load_dotenv()
API_KEY = os.getenv("SERPAPI_API_KEY")

def get_top_competitor_urls(keyword, num_results=5):
    # キーワードが無ければ呼ばない（SEOフォールバック廃止）
    if not keyword or not str(keyword).strip():
        return []

    params = {
        "engine": "google",
        "q": keyword,
        "api_key": API_KEY,
        "num": num_results,
        "hl": "ja",  # 日本語
        "gl": "jp",  # 日本
    }

    try:
        results = GoogleSearch(params).get_dict()
    except Exception as e:
        print(f"⚠️ SerpAPI通信エラー: {e}")
        return []

    if results.get("error"):
        print(f"⚠️ SerpAPIエラー: {results.get('error')}")
        return []

    comps = []
    for i, r in enumerate(results.get("organic_results", []), start=1):
        link  = r.get("link")
        title = r.get("title") or ""
        if link:
            comps.append({"position": i, "title": title, "url": link})
            if len(comps) >= num_results:
                break
    return comps

def get_meta_info_from_url(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, timeout=5, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        desc_tag = soup.find("meta", attrs={"name": "description"})
        description = (desc_tag.get("content") or "").strip() if desc_tag else ""
        return {"url": url, "title": title, "description": description}
    except Exception as e:
        print(f"⚠️ Meta取得エラー: {url} -> {e}")
        return {"url": url, "title": "", "description": ""}
