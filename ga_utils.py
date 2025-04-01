from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Metric, Dimension
import os
import base64
import pandas as pd

# Google Analyticsの認証
GA_PROPERTY_ID = "YOUR_GA4_PROPERTY_ID"
SERVICE_ACCOUNT_FILE = "ga_credentials.json"

if "GA_CREDS_BASE64" in os.environ:
    with open(SERVICE_ACCOUNT_FILE, "wb") as f:
        f.write(base64.b64decode(os.environ["GA_CREDS_BASE64"]))
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_ACCOUNT_FILE

client = BetaAnalyticsDataClient()

def fetch_ga_data(start_date: str, end_date: str):
    """Google Analytics からデータを取得"""
    
    request = RunReportRequest(
        property=f"properties/{GA_PROPERTY_ID}",
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=[
            Dimension(name="searchTerm"),  # 検索キーワード
            Dimension(name="sessionDefaultChannelGrouping")  # 流入チャネル
        ],
        metrics=[
            Metric(name="activeUsers"),  # アクティブユーザー数
            Metric(name="eventCount"),   # イベント数（コンバージョン含む）
            Metric(name="conversions")   # コンバージョン数
        ]
    )

    response = client.run_report(request)
    
    # データを pandas DataFrame に変換
    data = []
    for row in response.rows:
        data.append([row.dimension_values[0].value, row.dimension_values[1].value,
                     int(row.metric_values[0].value), int(row.metric_values[1].value),
                     int(row.metric_values[2].value)])
    
    df = pd.DataFrame(data, columns=["検索キーワード", "流入経路", "ユーザー数", "イベント数", "コンバージョン数"])
    return df
