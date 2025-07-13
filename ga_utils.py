from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Metric, Dimension
from google.oauth2 import service_account
import os
import base64
import pandas as pd
from urllib.parse import urlparse

# Google Analyticsの認証
GA_PROPERTY_ID = "483491280"
SERVICE_ACCOUNT_FILE = "credentials.json"

if "GOOGLE_CREDS_BASE64" in os.environ:
    with open(SERVICE_ACCOUNT_FILE, "wb") as f:
        f.write(base64.b64decode(os.environ["GOOGLE_CREDS_BASE64"]))

credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE)
client = BetaAnalyticsDataClient()


def fetch_ga_conversion_for_url(start_date: str, end_date: str, full_url: str):
    """指定されたパスに対応するGAのコンバージョンデータを取得"""
    request = RunReportRequest(
        property=f"properties/{GA_PROPERTY_ID}",
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=[
            Dimension(name="pagePath"),
        ],
        metrics=[
            Metric(name="conversions"),
        ],
        dimension_filter={
            "filter": {
                "field_name": "pagePath",
                "string_filter": {
                    "value": full_url,
                    "match_type": "EXACT"
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
    入力されたURL（例: https://www.example.com）から
    wwwを除去し、https付きのドメインを返す（例: https://example.com）
    """
    parsed = urlparse(site_url)
    return f"https://{parsed.netloc.replace('www.', '')}"
