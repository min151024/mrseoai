from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Metric, Dimension, Filter, FilterExpression
from google.oauth2 import service_account
from urllib.parse import urlparse
import os
import base64
import pandas as pd

# Google Analyticsの認証
GA_PROPERTY_ID = "483491280"
SERVICE_ACCOUNT_FILE = "credentials.json"

if "GOOGLE_CREDS_BASE64" in os.environ:
    with open(SERVICE_ACCOUNT_FILE, "wb") as f:
        f.write(base64.b64decode(os.environ["GOOGLE_CREDS_BASE64"]))

credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE)
client = BetaAnalyticsDataClient(credentials=credentials)

def extract_path_from_url(full_url: str) -> str:
    """フルURLからパスだけを抽出"""
    parsed_url = urlparse(full_url)
    return parsed_url.path or "/"

def fetch_ga_conversion_for_url(start_date: str, end_date: str, full_url: str):
    """指定したフルURLに対応するパスのコンバージョン数を取得"""
    page_path = extract_path_from_url(full_url)

    request = RunReportRequest(
        property=f"properties/{GA_PROPERTY_ID}",
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="conversions")],
        dimension_filter=FilterExpression(
            filter=Filter(
                field_name="pagePath",
                string_filter={"match_type": "EXACT", "value": page_path}
            )
        )
    )

    response = client.run_report(request)

    data = []
    for row in response.rows:
        data.append([row.dimension_values[0].value, int(row.metric_values[0].value)])

    df = pd.DataFrame(data, columns=["URL", "コンバージョン数"])
    return df

# 例:
# df = fetch_ga_conversion_for_url("2024-04-01", "2024-04-28", "https://example.com/page1")
# print(df)