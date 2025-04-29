import gspread
from oauth2client.service_account import ServiceAccountCredentials

SHEET_SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_FILE = 'credentials.json'

# gspread認証
credentials = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SHEET_SCOPES)
gc = gspread.authorize(credentials)

def get_spreadsheet(spreadsheet_id):
    """スプレッドシートを開く"""
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
