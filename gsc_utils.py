import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

SCOPES = ['https://www.googleapis.com/auth/webmasters.readonly']
SERVICE_ACCOUNT_FILE = 'credentials.json'

def get_search_console_service():
    credentials = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SCOPES)
    return build('searchconsole', 'v1', credentials=credentials)

def fetch_gsc_data(service, site_url, start_date, end_date):
    """Google Search Console からページデータを取得"""
    request = {
        'startDate': start_date.isoformat(),
        'endDate': end_date.isoformat(),
        'dimensions': ['query', 'page'],
        'rowLimit': 1000
    }
    try:
        response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
        rows = response.get('rows', [])
        data = []
        for row in rows:
            keys = row.get('keys', [])
            query = keys[0] if len(keys) > 0 else ''
            page = keys[1] if len(keys) > 1 else ''

            data.append([
                page,                          # URL
                row.get('clicks', 0),
                row.get('impressions', 0),
                round(row.get('ctr', 0) * 100, 2),  # CTR（%）
                round(row.get('position', 0), 2)    # 平均順位
            ])

        df = pd.DataFrame(data, columns=['URL', 'クリック数', '表示回数', 'CTR（%）', '平均順位'])
        return df

    except HttpError as error:
        print(f"❌ GSC API エラー: {error}")
        return pd.DataFrame(columns=['URL', 'クリック数', '表示回数', 'CTR（%）', '平均順位'])
