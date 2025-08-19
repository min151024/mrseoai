import gspread
from google.auth import default as google_auth_default  # ★ ADC
# oauth2client / credentials.json は使わない

# 推奨スコープ（/feeds は古いので置き換え）
SHEET_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_gc = None
def get_gspread_client():
    """ADCで認証した gspread クライアント（遅延初期化）"""
    global _gc
    if _gc is None:
        creds, _ = google_auth_default(scopes=SHEET_SCOPES)
        _gc = gspread.authorize(creds)
    return _gc

def get_spreadsheet(spreadsheet_id):
    """スプレッドシートを開く"""
    return get_gspread_client().open_by_key(spreadsheet_id)

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
    """指定したシートをクリアしてデータを書き込む（まとめて更新）"""
    worksheet.clear()
    # A1 からヘッダー＋データを一括更新（APIコールを削減）
    values = [headers] + data
    worksheet.update('A1', values)

def write_competitor_data_to_sheet(spreadsheet, competitor_data):
    worksheet = get_or_create_worksheet(spreadsheet, "競合分析")
    headers = ["URL", "タイトル", "メタディスクリプション"]
    values = [[c["URL"], c["タイトル"], c["メタディスクリプション"]] for c in competitor_data]
    update_sheet(worksheet, headers, values)
