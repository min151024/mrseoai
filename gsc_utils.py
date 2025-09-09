import pandas as pd
from urllib.parse import urlparse
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- ユーザーOAuthの Credentials を受け取って使う -----------------------------

def get_search_console_service(creds):
    """Search Console v1 クライアント（ユーザーOAuthで）"""
    return build('searchconsole', 'v1', credentials=creds, cache_discovery=False)

def list_sc_sites(creds) -> list[str]:
    """
    （任意）ユーザーがアクセス権のあるサイト一覧を取得。
    Search Console のサイト列挙は webmasters v3 を使うのが安定。
    """
    svc = build('webmasters', 'v3', credentials=creds, cache_discovery=False)
    res = svc.sites().list().execute()
    sites = []
    for entry in res.get('siteEntry', []):
        # 未確認サイトは除外
        if entry.get('permissionLevel') != 'siteUnverifiedUser':
            sites.append(entry.get('siteUrl'))
    return sites

# --- ユーティリティ -----------------------------------------------------------

def _iso(d) -> str:
    """date/datetime/str を ISO8601 っぽい文字列に揃える"""
    try:
        return d.isoformat()
    except AttributeError:
        return str(d)

def normalize_url(url: str) -> str:
    """
    URL を https固定・www除去・パス必須 で正規化
    例: http://www.example.com → https://example.com/
    """
    if not url:
        return ''
    if not url.startswith(('http://','https://')):
        url = 'https://' + url.lstrip('/')
    p = urlparse(url)
    scheme = p.scheme or 'https'
    netloc = (p.netloc or '').replace('www.', '')
    path = p.path or '/'
    return f"{scheme}://{netloc}{path}"

# --- メイン：検索アナリティクス ------------------------------------------------

def fetch_gsc_data(
    *,
    creds,                 # ★ ユーザーOAuthの Credentials
    sc_property: str,      # ★ "sc-domain:example.com" または "https://example.com/"
    start_date,            # date/datetime/str どれでもOK
    end_date,              # date/datetime/str どれでもOK
    row_limit: int = 25000,
    url_filter: str | None = None,   # ページに contains フィルタを掛けたいとき
) -> pd.DataFrame:
    """
    Search Console Search Analytics API v1 を叩いて
    [query, page] 単位の指標を DataFrame で返す。
    """
    svc = get_search_console_service(creds)

    body = {
        'startDate': _iso(start_date),
        'endDate': _iso(end_date),
        'dimensions': ['page', 'query'],   # ← page を先に（扱いやすい）
        'rowLimit': row_limit,
    }
    if url_filter:
        body['dimensionFilterGroups'] = [{
            'filters': [{
                'dimension': 'page',
                'operator': 'contains',
                'expression': url_filter
            }]
        }]

    try:
        resp = svc.searchanalytics().query(siteUrl=sc_property, body=body).execute()
        rows = resp.get('rows', [])
        data = []
        for r in rows:
            keys = r.get('keys', [])
            page = keys[0] if len(keys) > 0 else ''
            query = keys[1] if len(keys) > 1 else ''
            clicks = r.get('clicks', 0) or 0
            imps   = r.get('impressions', 0) or 0
            ctr    = r.get('ctr', 0.0) or 0.0
            pos    = r.get('position', 0.0) or 0.0
            data.append([
                query,
                normalize_url(page) if page else '',
                clicks,
                imps,
                round(ctr * 100, 2),     # → %
                round(pos, 2),
            ])

        return pd.DataFrame(
            data,
            columns=['検索キーワード', 'URL', 'クリック数', '表示回数', 'CTR（%）', '平均順位']
        )

    except HttpError as e:
        print("❌ GSC API エラー:", e)
        return pd.DataFrame(columns=['検索キーワード', 'URL', 'クリック数', '表示回数', 'CTR（%）', '平均順位'])
