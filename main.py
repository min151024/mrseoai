import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from serp_api_utils import get_top_competitor_urls, get_meta_info_from_url
from chatgpt_utils import build_prompt, get_chatgpt_response
import os
import base64
from googleapiclient.errors import HttpError


# ==========
# 認証部分
# ==========
SCOPES = ['https://www.googleapis.com/auth/webmasters.readonly']
SHEET_SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_FILE = 'credentials.json'

# Render上に環境変数がある場合、それをデコードして credentials.json を作成
if "GOOGLE_CREDS_BASE64" in os.environ:
    with open(SERVICE_ACCOUNT_FILE, "wb") as f:
        f.write(base64.b64decode(os.environ["GOOGLE_CREDS_BASE64"]))
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_ACCOUNT_FILE

# credentials.json を使って認証
credentials = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SHEET_SCOPES)
gc = gspread.authorize(credentials)


SPREADSHEET_ID = '1Fpdb-3j89j7OkPmJXbdmSmFBaA6yj2ZB0AUBNvF6BQ4'  # ← スプレッドシートIDを自分のものに変更

def fetch_data(service, site_url, start_date, end_date):
    try:
        request = {
            'startDate': start_date.isoformat(),
            'endDate': end_date.isoformat(),
            'dimensions': ['page'],
            'rowLimit': 1000
        }
        response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
        rows = response.get('rows', [])

        if not rows:
            print(f"⚠️ URL {site_url} のデータが見つかりませんでした。")
            return pd.DataFrame(columns=['URL', 'クリック数', '表示回数', 'CTR（%）', '平均順位'])

        data = [
            [row['keys'][0], row.get('clicks', 0), row.get('impressions', 0), row.get('ctr', 0) * 100, row.get('position', 0)]
            for row in rows
        ]
        return pd.DataFrame(data, columns=['URL', 'クリック数', '表示回数', 'CTR（%）', '平均順位'])

    except HttpError as e:
        print(f"🚨 Google Search Console の API エラー: {e}")
        return None
    
#----------------------------------------------------------

def process_seo_improvement(site_url):
    """指定したURLのSEO改善を実行"""
    print(f"🚀 SEO改善を開始: {site_url}")

    # Google Search Console API 認証
    credentials = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SCOPES)
    service = build('searchconsole', 'v1', credentials=credentials)

    # 日付設定（過去7日間とその前の7日間）
    today = datetime.today().date()
    this_week_start = today - timedelta(days=7)
    this_week_end = today
    last_week_start = today - timedelta(days=14)
    last_week_end = today - timedelta(days=7)

    # Google Search Console からデータ取得
    df_this_week = fetch_data(service, site_url, this_week_start, this_week_end)
    df_last_week = fetch_data(service, site_url, last_week_start, last_week_end)


    print(df_this_week.head())

    # Google Sheets 取得
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)

    try:
        sheet_suggestions = spreadsheet.worksheet("改善案")
        print("✅ 既存の『改善案』シートを使用します。")
    except gspread.exceptions.WorksheetNotFound:
        sheet_suggestions = spreadsheet.add_worksheet(title="改善案", rows="100", cols="20")
        print("🆕 新しく『改善案』シートを作成しました。")

    # スプレッドシートに今週のデータを書き込む
    sheet_suggestions.clear()
    sheet_suggestions.append_row(['URL', 'クリック数', '表示回数', 'CTR（%）', '平均順位'])
    for row in df_this_week.values.tolist():
        sheet_suggestions.append_row(row)

    # 順位変化を計算
    merged_df = pd.merge(df_last_week, df_this_week, on='URL', suffixes=('_先週', '_今週'))
    merged_df['順位変化'] = merged_df['平均順位_今週'] - merged_df['平均順位_先週']
    dropped_df = merged_df[merged_df['順位変化'] > 0].sort_values(by='順位変化', ascending=False)

    if dropped_df.empty:
        print("❌ 順位が下がったページが見つかりませんでした。")
        return

    # 順位が下がったページの中から1ページを選ぶ
    target_url = dropped_df.iloc[0]['URL']
    print(f"🎯 対象ページ: {target_url}")

    # メタ情報・キーワード取得
    try:
        meta_info = get_meta_info_from_url(target_url)
        keyword = meta_info.get("title") or meta_info.get("description") or "SEO"
        print(f"🔍 抽出されたキーワード: {keyword}")
    except Exception as e:
        print(f"⚠️ メタ情報の取得に失敗: {e}")
        return

    # 競合ページ取得
    try:
        top_urls = get_top_competitor_urls(keyword)
        competitors_info = [get_meta_info_from_url(url) for url in top_urls if url]
    except Exception as e:
        print(f"⚠️ 競合ページの取得に失敗: {e}")
        competitors_info = []

    # ChatGPT に改善案を依頼
    try:
        prompt = build_prompt(target_url, competitors_info)
        response = get_chatgpt_response(prompt)
        print("💡 ChatGPT改善案:\n", response)
    except Exception as e:
        print(f"⚠️ ChatGPTへのリクエスト失敗: {e}")

        response = "ChatGPT からの改善提案を取得できませんでした。"

        result_html = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SEO 改善提案</title>
    </head>
    <body>
        <h2>SEO 改善提案</h2>
        <p><strong>対象URL：</strong> {target_url}</p>
        <h3>💡 ChatGPTの改善提案</h3>
        <p>{response}</p>
        <a href="/">戻る</a>
    </body>
    </html>
    """

    with open("templates/result.html", "w", encoding="utf-8") as f:
        f.write(result_html)

    return response