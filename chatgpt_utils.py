import os
from openai import OpenAI
import pandas as pd
import requests
from bs4 import BeautifulSoup

# --- OpenAIクライアントを遅延初期化（起動時クラッシュ防止） ---
_client = None
def get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            # 起動エラーは避け、呼び出し時に明示エラー
            raise RuntimeError("OPENAI_API_KEY が未設定です（Cloud Run の環境変数に設定してください）")
        _client = OpenAI(api_key=api_key)
        # もしくは _client = OpenAI() でもOK（環境変数を自動検出）
    return _client

def fetch_service_description(url: str) -> str:
    """ターゲット URL からサイトの自己紹介文（meta description, og:description, h1＋p）を取得する"""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, timeout=5, headers=headers)
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
    lines = []
    for comp in competitors_info or []:
        title = comp.get("title", comp.get("タイトル", "タイトルなし"))
        description = comp.get("description", comp.get("メタディスクリプション", "ディスクリプションなし"))
        lines.append(f"・タイトル: {title}\n  ディスクリプション: {description}")
    competitors_text = "\n\n".join(lines) if lines else "（競合メタ情報なし）"

    # Google Analyticsデータをテキスト化
    if isinstance(ga_data, pd.DataFrame) and not ga_data.empty:
        ga_text = ga_data.to_string(index=False)
    else:
        ga_text = "Google Analytics データなし"

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

def get_chatgpt_response(prompt: str) -> str | None:
    """OpenAIに投げて応答を返す"""
    try:
        client = get_openai_client()
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # 任意で上書き可。旧: gpt-3.5-turbo
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "あなたはSEOの専門家です。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print("❌ ChatGPT APIエラー:", e)
        return None
