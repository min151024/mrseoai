import gspread

# gspread は引数で渡されたユーザーOAuth Credentialsを利用します
# （ADC/サービスアカウントは使いません）

def get_gspread_client(creds):
    """ユーザーOAuthのCredentialsから gspread クライアントを作成"""
    return gspread.authorize(creds)

def get_spreadsheet(creds, spreadsheet_id):
    """スプレッドシートを開く（ユーザーの権限で）"""
    gc = get_gspread_client(creds)
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
    """指定したシートをクリアしてデータを書き込む（まとめて更新）"""
    worksheet.clear()
    values = [headers] + data
    worksheet.update('A1', values)

def write_competitor_data_to_sheet(spreadsheet, competitor_data):
    worksheet = get_or_create_worksheet(spreadsheet, "競合分析")
    headers = ["URL", "タイトル", "メタディスクリプション"]
    values = [[c.get("URL",""), c.get("タイトル",""), c.get("メタディスクリプション","")] for c in competitor_data]
    update_sheet(worksheet, headers, values)

# （任意）新規スプレッドシートをユーザーのDrive上に作成したいとき
def create_spreadsheet(creds, title="Mr.SEO 出力シート"):
    gc = get_gspread_client(creds)
    sh = gc.create(title)
    print(f"🆕 スプレッドシートを作成: {sh.id}")
    return sh
