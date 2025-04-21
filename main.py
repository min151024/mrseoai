import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from serp_api_utils import get_top_competitor_urls, get_meta_info_from_url
from chatgpt_utils import build_prompt, get_chatgpt_response
import os
import base64
from googleapiclient.errors import HttpError
from flask import render_template
from ga_utils import fetch_ga_data


# ==========
# 認証部分
# ==========
SERVICE_ACCOUNT_FILE = 'credentials.json'

# Render上に環境変数がある場合、それをデコードして credentials.json を作成
if "GOOGLE_CREDS_BASE64" in os.environ:
    with open(SERVICE_ACCOUNT_FILE, "wb") as f:
        f.write(base64.b64decode(os.getenv("GOOGLE_CREDS_BASE64")))

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials.json"

SPREADSHEET_ID = '1Fpdb-3j89j7OkPmJXbdmSmFBaA6yj2ZB0AUBNvF6BQ4'
SCOPES = ['https://www.googleapis.com/auth/webmasters.readonly']
SHEET_SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# gspread用の認証
credentials = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SHEET_SCOPES)
gc = gspread.authorize(credentials)

# Google Sheets API用の認証
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets"])
service = build("sheets", "v4", credentials=creds)

def fetch_date(gsc_data):
    """Google Search ConsoleデータとGAデータをスプレッドシートに書き込む"""

    # Google Analytics データを取得
    today = datetime.today().date()
    start_date = (today - timedelta(days=7)).isoformat()
    end_date = today.isoformat()
    ga_data = fetch_ga_data(start_date, end_date)

    # Spreadsheet 認証と取得
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)

    # 「SEO_Data」シートの取得（なければ作成）
    try:
        sheet = spreadsheet.worksheet("順位が下がったページ")
        print("✅ 『順位が下がったページ』シートを使用します。")
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title="SEO_Data", rows="100", cols="20")
        print("🆕 『順位が下がったページ』シートを新規作成しました。")

    # クリア
    sheet.clear()

    # GSCヘッダー
    gsc_values = [["URL", "検索キーワード", "平均順位", "クリック数", "表示回数"]]

    # GSCデータが空でない場合に追加
    if gsc_data:
        print(f"📊 GSCデータ件数: {len(gsc_data)}")
        for row in gsc_data:
            gsc_values.append([
                row.get("url", "なし"),
                row.get("query", "なし"),
                row.get("position", "なし"),
                row.get("clicks", "なし"),
                row.get("impressions", "なし")
            ])
    else:
        print("⚠️ GSCデータが空でした。")
        gsc_values.append(["データなし", "", "", "", ""])

    # GSCデータ書き込み（A1から）
    sheet.update(values=gsc_values, range_name="A1")

    # GAヘッダー
    ga_values = [["検索キーワード", "流入経路", "ユーザー数", "イベント数", "コンバージョン数"]]

    if ga_data is None or ga_data.empty:
        print("⚠️ Google Analytics データが取得できませんでした。")
        ga_values.append(["データなし", "", "", "", ""])
    else:
        for _, row in ga_data.iterrows():
            ga_values.append([
                row.get("検索キーワード", "なし"),
                row.get("流入経路", "なし"),
                row.get("ユーザー数", 0),
                row.get("イベント数", 0),
                row.get("コンバージョン数", 0)
            ])

    # GAデータ書き込み（G1から）
    sheet.update(values=ga_values, range_name="G1")

    print("✅ スプレッドシートにデータを出力しました！")


def fetch_data(service, site_url, start_date, end_date):
    """Google Search Console からデータを取得"""
    request = {
        'startDate': start_date.isoformat(),
        'endDate': end_date.isoformat(),
        'dimensions': ['query', 'page'],
        'rowLimit': 1000
    }
    try:
        response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
        rows = response.get('rows', [])

        # データを pandas の DataFrame に変換
        data = []
        for row in rows:
            data.append([
                row['keys'][0],  # URL
                row.get('clicks', 0),
                row.get('impressions', 0),
                row.get('ctr', 0) * 100,  # CTR（% に変換）
                row.get('position', 0)
            ])

        df = pd.DataFrame(data, columns=['URL', 'クリック数', '表示回数', 'CTR（%）', '平均順位'])
        return df
    except HttpError as error:
        print(f"❌ Google Search Console API エラー: {error}")
        return pd.DataFrame(columns=['URL', 'クリック数', '表示回数', 'CTR（%）', '平均順位'])


    
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

    print("last_week rows:", len(df_last_week))
    print("this_week rows:", len(df_this_week))



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

    gsc_data_for_export = []
    for _, row in df_this_week.iterrows():
     gsc_data_for_export.append({
        "url": row["URL"],
        "query": "（仮）",  # query がないので仮に埋める
        "position": row["平均順位"],
        "clicks": row["クリック数"],
        "impressions": row["表示回数"]
    })

# スプレッドシート書き出し実行
    fetch_date(gsc_data_for_export)

    # 順位変化を計算
    merged_df = pd.merge(df_last_week, df_this_week, on='URL', suffixes=('_先週', '_今週'))
    merged_df['順位変化'] = merged_df['平均順位_今週'] - merged_df['平均順位_先週']
    dropped_df = merged_df[merged_df['順位変化'] > 0].sort_values(by='順位変化', ascending=False)

# 💡 スプレッドシートに「順位が下がったページ」シートを更新
    try:
      sheet_dropped = spreadsheet.worksheet("順位が下がったページ")
      print("✅ 『順位が下がったページ』シートを使用します。")
    except gspread.exceptions.WorksheetNotFound:
      sheet_dropped = spreadsheet.add_worksheet(title="順位が下がったページ", rows="100", cols="20")
      print("🆕 『順位が下がったページ』シートを新規作成しました。")

# 上書きでクリア＆データ追加
    sheet_dropped.clear()
    sheet_dropped.append_row(['URL', '平均順位（先週）', '平均順位（今週）', '順位変化'])
    for _, row in dropped_df.iterrows():
        sheet_dropped.append_row([
            row['URL'],
            row['平均順位_先週'],
            row['平均順位_今週'],
            row['順位変化']
        ])

    if dropped_df.empty:
        print("❌ 順位が下がったページが見つかりませんでした。")

        # 順位が最も低いページを代わりに選ぶ
        all_df = pd.merge(df_last_week, df_this_week, on='URL', suffixes=('_先週', '_今週'))
        worst_page = all_df.sort_values(by='平均順位_今週', ascending=False).iloc[0]
        target_url = worst_page['URL']
        print(f"🎯 順位が下がったページがないため、平均順位が最も悪いページを対象に設定: {target_url}")
    else:
        # 順位が下がったページの中から1ページを選ぶ
        target_url = dropped_df.iloc[0]['URL']
        print(f"🎯 順位が下がったページの中から対象ページを設定: {target_url}")

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
    data = df_this_week.values.tolist() 
    table_html = "<table border='1'><tr><th>URL</th><th>検索クエリ</th><th>クリック数</th><th>表示回数</th><th>CTR</th><th>平均順位</th></tr>"
    for row in data:
        table_html += "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
    table_html += "</table>"


    # HTMLテンプレートにデータを渡して出力
    data = df_this_week.values.tolist() if df_this_week is not None else []

# `result.html` に保存
    with open("templates/result.html", "w", encoding="utf-8") as f:
      f.write(result_html)

    print("✅ HTMLファイルに出力しました。")

# スプレッドシートに今週のデータを書き込む
    if df_this_week is not None and not df_this_week.empty:
     sheet_suggestions.clear()
     sheet_suggestions.append_row(['URL', 'クリック数', '表示回数', 'CTR（%）', '平均順位'])
     for row in df_this_week.values.tolist():
        sheet_suggestions.append_row(row)
    else:
     print("❌ Google Search Console のデータが取得できませんでした。")

    return result_html

if __name__ == "__main__":
    process_seo_improvement("https://mrseoai.com")