from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Metric, Dimension
from google.oauth2 import service_account
import os
import base64
import pandas as pd
from urllib.parse import urlparse
import config
from flask import abort

# Google Analyticsの認証
SERVICE_ACCOUNT_FILE = "credentials.json"

if "GOOGLE_CREDS_BASE64" in os.environ:
    with open(SERVICE_ACCOUNT_FILE, "wb") as f:
        f.write(base64.b64decode(os.environ["GOOGLE_CREDS_BASE64"]))

credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE)
client = BetaAnalyticsDataClient()


def to_ga_property(url: str) -> str:
    """
    URL（ドメイン or URLプレフィックス）から
    config.GA_PROPERTY_MAP を参照して properties/{ID} を返す
    """
    # スキーム補完
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    hostname = parsed.hostname
    if hostname is None:
        abort(400, f"URLが不正です: {url}")

    # 1) URLプレフィックス文字列
    prefix = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
    # 2) ドメイン文字列
    domain = hostname.replace("www.", "")

    # プレフィックス優先 → ドメイン
    if prefix in config.GA_PROPERTY_MAP:
        prop_id = config.GA_PROPERTY_MAP[prefix]
    elif domain in config.GA_PROPERTY_MAP:
        prop_id = config.GA_PROPERTY_MAP[domain]
    else:
        abort(400, f"GA プロパティID が設定にありません: {prefix} または {domain}")

    return f"properties/{prop_id}"


def fetch_ga_conversion_for_url(start_date: str, end_date: str, full_url: str) -> pd.DataFrame:
    """
    指定されたURL（ドメイン or サブパス）に対応する GA のコンバージョンデータを取得
    """
    ga_prop = to_ga_property(full_url)

    # ページパス部分だけ取り出す（"/" 以上を正確にマッチさせる）
    parsed = urlparse(full_url if full_url.startswith(("http://","https://")) else "https://" + full_url)
    path = parsed.path or "/"

    request = RunReportRequest(
        property=ga_prop,
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="conversions")],
        dimension_filter={
            "filter": {
                "fieldName": "pagePath",
                "stringFilter": {
                    "matchType": "EXACT",
                    "value": path
                }
            }
        }
    )

    response = client.run_report(request)

    data = []
    for row in response.rows:
        data.append({
            "URL": row.dimension_values[0].value,
            "コンバージョン数": int(row.metric_values[0].value)
        })

    return pd.DataFrame(data)


def get_domain_from_url(site_url: str) -> str:
    """
    （変更なし）https://www.example.com → https://example.com
    """
    parsed = urlparse(site_url if site_url.startswith(("http://","https://")) else "https://" + site_url)
    return f"https://{parsed.netloc.replace('www.', '')}"