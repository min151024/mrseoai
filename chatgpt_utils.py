import os
from openai import OpenAI
import pandas as pd
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def fetch_service_description(url: str) -> str:
    """ターゲット URL からサイトの自己紹介文（meta description, og:description, h1＋p）を取得する"""
    try:
        res = requests.get(url, timeout=5)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        # 1) meta description
        desc = soup.find("meta", {"name":"description"})
        if desc and desc.get("content"):
            return desc["content"].strip()

        # 2) og:description
        desc = soup.find("meta", {"property":"og:description"})
        if desc and desc.get("content"):
            return desc["content"].strip()

        # 3) h1 + 最初の段落
        h1 = soup.find("h1")
        p  = soup.find("p")
        parts = []
        if h1: parts.append(h1.get_text().strip())
        if p:  parts.append(p.get_text().strip())
        if parts:
            return "／".join(parts)

    except Exception:
        pass  # スクレイピング失敗時は空文字を返す

    return ""

def build_prompt(target_url, competitors_info, ga_data):
    """対象URL、競合ページ情報、GAデータからChatGPT用のプロンプトを作成する"""
    service_desc = fetch_service_description(target_url)
    # 競合ページ情報をテキスト化
    competitors_text = ""
    for comp in competitors_info:
        title = comp.get("title", "タイトルなし")
        description = comp.get("description", "ディスクリプションなし")
        competitors_text += f"・タイトル: {title}\n  ディスクリプション: {description}\n\n"

    # Google Analyticsデータをテキスト化
    if ga_data is not None and not ga_data.empty:
        ga_text = ga_data.to_string(index=False)
    else:
        ga_text = "Google Analytics データなし"

    # 最終プロンプト組み立て
    prompt = f"""
対象ページ: {target_url}

【サイトのサービス紹介】
{service_desc or 'サイト自己紹介文なし'}

【競合ページのメタ情報】
{competitors_text}

【対象ページのGoogle Analyticsデータ】
{ga_text}

上記を参考にして、対象ページのタイトルとメタディスクリプションの改善案を日本語で提案してください。
"""
    return prompt

# ChatGPTに投げる
def get_chatgpt_response(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # または "gpt-4"
            messages=[
                {"role": "system", "content": "あなたはSEOの専門家です。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("❌ ChatGPT APIエラー:", e)
        return None
