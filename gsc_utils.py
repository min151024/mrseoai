import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth import default as google_auth_default 
from urllib.parse import urlparse

SCOPES = ['https://www.googleapis.com/auth/webmasters.readonly']

def get_search_console_service():
    creds, _ = google_auth_default(scopes=SCOPES)
    return build('searchconsole', 'v1', credentials=creds, cache_discovery=False)

def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = "https"  # 絶対に https に固定
    netloc = parsed.netloc.replace("www.", "")  # www を除去
    return f"{scheme}://{netloc}{parsed.path or '/'}"

def fetch_gsc_data(service, site_url, start_date, end_date):
    """GSCからクエリとページのデータを取得、URL正規化"""
    request = {
        'startDate': start_date.isoformat(),
        'endDate': end_date.isoformat(),
        'dimensions': ['query', 'page'],
        'rowLimit': 1000
    }
    try:
        response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
        print("📡 GSC APIレスポンス:", response)
        rows = response.get('rows', [])
        data = []
        for row in rows:
            keys = row.get('keys', [])
            if len(keys) < 2:
               continue 

            query = keys[0] if len(keys) > 0 else ''
            page = keys[1] if len(keys) > 1 else ''
            normalized_page = normalize_url(page) if page else ''  

            data.append([
                query,
                normalized_page,
                row.get('clicks', 0),
                row.get('impressions', 0),
                round(row.get('ctr', 0) * 100, 2),
                round(row.get('position', 0), 2)
            ])

        df = pd.DataFrame(data, columns=['検索キーワード', 'URL', 'クリック数', '表示回数', 'CTR（%）', '平均順位'])
        return df


    except HttpError as error:
        print(f"❌ GSC API エラー: {error}")
        return pd.DataFrame(columns=['検索キーワード', 'URL', 'クリック数', '表示回数', 'CTR（%）', '平均順位'])
