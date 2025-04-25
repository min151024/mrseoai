
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from ga_utils import fetch_ga_data
from datetime import datetime, timedelta

SHEET_SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_FILE = 'credentials.json'

# gspread認証
credentials = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SHEET_SCOPES)
gc = gspread.authorize(credentials)

def fetch_date_to_sheet(spreadsheet_id, gsc_data):
    """GSC + GA データを指定スプレッドシートに出力"""
    spreadsheet = gc.open_by_key(spreadsheet_id)

    today = datetime.today().date()
    start_date = (today - timedelta(days=7)).isoformat()
    end_date = today.isoformat()
    ga_data = fetch_ga_data(start_date, end_date)

    try:
        sheet = spreadsheet.worksheet("順位が下がったページ")
        print("✅ 『順位が下がったページ』シートを使用します。")
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title="SEO_Data", rows="100", cols="20")
        print("🆕 『順位が下がったページ』シートを新規作成しました。")

    sheet.clear()

    gsc_values = [["URL", "検索キーワード", "平均順位", "クリック数", "表示回数"]]
    if gsc_data:
        for row in gsc_data:
            gsc_values.append([
                row.get("url", "なし"),
                row.get("query", "なし"),
                row.get("position", "なし"),
                row.get("clicks", "なし"),
                row.get("impressions", "なし")
            ])
    else:
        gsc_values.append(["データなし", "", "", "", ""])

    sheet.update(values=gsc_values, range_name="A1")

    ga_values = [["検索キーワード", "流入経路", "ユーザー数", "イベント数", "コンバージョン数"]]
    if ga_data is None or ga_data.empty:
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

    sheet.update(values=ga_values, range_name="G1")
    print("✅ スプレッドシートにデータを出力しました！")

def get_spreadsheet(spreadsheet_id):
    return gc.open_by_key(spreadsheet_id)

def get_or_create_worksheet(spreadsheet, title, rows="100", cols="20"):
    """既存シートを取得 or なければ作成"""
    try:
        worksheet = spreadsheet.worksheet(title)
        print(f"✅ 既存の『{title}』シートを使用します。")
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)
        print(f"🆕 『{title}』シートを新規作成しました。")
    return worksheet

def update_sheet(worksheet, headers, data):
    """指定したシートをクリアしてデータを書き込む"""
    worksheet.clear()
    worksheet.append_row(headers)
    for row in data:
        worksheet.append_row(row)

def write_gsc_data_to_sheet(spreadsheet, gsc_data):
    worksheet = get_or_create_worksheet(spreadsheet, "順位が下がったページ")
    headers = ["URL", "検索キーワード", "平均順位", "クリック数", "表示回数"]
    values = []

    if gsc_data:
        for row in gsc_data:
            values.append([
                row.get("url", "なし"),
                row.get("query", "なし"),
                row.get("position", "なし"),
                row.get("clicks", "なし"),
                row.get("impressions", "なし")
            ])
    else:
        values.append(["データなし", "", "", "", ""])

    update_sheet(worksheet, headers, values)

def write_ga_data_to_sheet(spreadsheet, ga_df):
    worksheet = get_or_create_worksheet(spreadsheet, "順位が下がったページ")
    headers = ["検索キーワード", "流入経路", "ユーザー数", "イベント数", "コンバージョン数"]
    values = []

    if ga_df is None or ga_df.empty:
        values.append(["データなし", "", "", "", ""])
    else:
        for _, row in ga_df.iterrows():
            values.append([
                row.get("検索キーワード", "なし"),
                row.get("流入経路", "なし"),
                row.get("ユーザー数", 0),
                row.get("イベント数", 0),
                row.get("コンバージョン数", 0)
            ])

    worksheet.update(values=values, range_name="G1")

