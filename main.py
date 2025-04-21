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

    # スプレッドシートのデータフォーマット
    gsc_values = [["URL", "検索キーワード", "平均順位", "クリック数", "表示回数"]]
    ga_values = [["検索キーワード", "流入経路", "ユーザー数", "イベント数", "コンバージョン数"]]

    # GSCデータをリスト化
    for row in gsc_data:
        gsc_values.append([row["url"], row["query"], row["position"], row["clicks"], row["impressions"]])

    # GAデータをリスト化
    if ga_data is None or ga_data.empty:
      print("⚠️ Google Analytics データが取得できませんでした。")
      ga_values.append(["データなし", "", "", "", ""])
    else:
      for _, row in ga_data.iterrows():
        ga_values.append([row["検索キーワード"], row["流入経路"], row["ユーザー数"], row["イベント数"], row["コンバージョン数"]])


    # Google Sheetsに書き込み
    sheet = service.spreadsheets()
    sheet.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"SEO_Data!A1",
        valueInputOption="RAW",
        body={"values": gsc_values}
    ).execute()

    sheet.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"SEO_Data!G1",  # GAデータはG列から開始
        valueInputOption="RAW",
        body={"values": ga_values}
    ).execute()

    print("スプレッドシートにデータを出力しました！")

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
    print(f"🚀 SEO改善を開始: {site_url}")

    # ① Google Search Console認証
    try:
        credentials = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SCOPES)
        print("✅ GSC認証完了")
    except Exception as e:
        print(f"❌ GSC認証失敗: {e}")
        return "エラー: GSC認証失敗"

    # ② Search Console APIサーバー接続
    try:
        service = build('searchconsole', 'v1', credentials=credentials)
        print("✅ Search Console サービス作成成功")
    except Exception as e:
        print(f"❌ Search Console サービス作成失敗: {e}")
        return "エラー: サービス作成失敗"

    # ③ 日付計算
    today = datetime.today().date()
    this_week_start = today - timedelta(days=7)
    this_week_end = today
    last_week_start = today - timedelta(days=14)
    last_week_end = today - timedelta(days=7)
    print("✅ 日付設定完了")

    # ④ Search Consoleデータ取得
    try:
        df_this_week = fetch_data(service, site_url, this_week_start, this_week_end)
        df_last_week = fetch_data(service, site_url, last_week_start, last_week_end)
        print(f"✅ GSCデータ取得完了。今週: {len(df_this_week)}行、先週: {len(df_last_week)}行")
    except Exception as e:
        print(f"❌ GSCデータ取得失敗: {e}")
        return "エラー: データ取得失敗"

    # ⑤ 順位が下がったページ抽出
    try:
        merged_df = pd.merge(df_last_week, df_this_week, on='URL', suffixes=('_先週', '_今週'))
        merged_df['順位変化'] = merged_df['平均順位_今週'] - merged_df['平均順位_先週']
        dropped_df = merged_df[merged_df['順位変化'] > 0].sort_values(by='順位変化', ascending=False)
        print(f"✅ 順位下がったページ数: {len(dropped_df)}")
    except Exception as e:
        print(f"❌ 順位変化計算失敗: {e}")
        return "エラー: 順位計算失敗"

    if dropped_df.empty:
        print("❌ 順位下がったページがありません。")
        return "エラー: 順位下がったページなし"

    # ⑥ ターゲットURL抽出
    target_url = dropped_df.iloc[0]['URL']
    print(f"🎯 対象ページURL抽出: {target_url}")

    # ⑦ 競合情報取得
    try:
        meta_info = get_meta_info_from_url(target_url)
        keyword = meta_info.get("title") or meta_info.get("description") or "SEO"
        print(f"🔍 抽出されたキーワード: {keyword}")
    except Exception as e:
        print(f"⚠️ メタ情報の取得失敗: {e}")
        return "エラー: メタ情報取得失敗"

    try:
        top_urls = get_top_competitor_urls(keyword)
        competitors_info = [get_meta_info_from_url(url) for url in top_urls if url]
        print(f"✅ 競合ページ取得完了: {len(competitors_info)}件")
    except Exception as e:
        print(f"⚠️ 競合ページ取得失敗: {e}")
        competitors_info = []

    # ⑧ ChatGPTに改善案依頼
    try:
        from ga_utils import fetch_ga_data
        start_date = (datetime.today() - timedelta(days=7)).isoformat()
        end_date = datetime.today().isoformat()
        ga_data = fetch_ga_data(start_date, end_date)
        print("✅ GAデータ取得完了")

        from chatgpt_utils import build_prompt, get_chatgpt_response
        prompt = build_prompt(target_url, competitors_info, ga_data)
        response = get_chatgpt_response(prompt)
        print(f"💡 ChatGPT改善案取得完了")
    except Exception as e:
        print(f"⚠️ ChatGPTへのリクエスト失敗: {e}")
        return "エラー: ChatGPTリクエスト失敗"

    return response


#         result_html = f"""
#     <!DOCTYPE html>
#     <html lang="ja">
#     <head>
#         <meta charset="UTF-8">
#         <meta name="viewport" content="width=device-width, initial-scale=1.0">
#         <title>SEO 改善提案</title>
#     </head>
#     <body>
#         <h2>SEO 改善提案</h2>
#         <p><strong>対象URL：</strong> {target_url}</p>
#         <h3>💡 ChatGPTの改善提案</h3>
#         <p>{response}</p>
#         <a href="/">戻る</a>
#     </body>
#     </html>
#     """
#     data = df_this_week.values.tolist() 
#     table_html = "<table border='1'><tr><th>URL</th><th>検索クエリ</th><th>クリック数</th><th>表示回数</th><th>CTR</th><th>平均順位</th></tr>"
#     for row in data:
#         table_html += "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
#     table_html += "</table>"


#     # HTMLテンプレートにデータを渡して出力
#     data = df_this_week.values.tolist() if df_this_week is not None else []

# # `result.html` に保存
#     with open("templates/result.html", "w", encoding="utf-8") as f:
#       f.write(result_html)

#     print("✅ HTMLファイルに出力しました。")

# # スプレッドシートに今週のデータを書き込む
#     if df_this_week is not None and not df_this_week.empty:
#      sheet_suggestions.clear()
#      sheet_suggestions.append_row(['URL', 'クリック数', '表示回数', 'CTR（%）', '平均順位'])
#      for row in df_this_week.values.tolist():
#         sheet_suggestions.append_row(row)
#     else:
#      print("❌ Google Search Console のデータが取得できませんでした。")

#     return result_html
