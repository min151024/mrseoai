from urllib.parse import urlparse
import pandas as pd

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest, DateRange, Metric, Dimension,
    Filter, FilterExpression
)

def _as_property_str(prop) -> str:
    """ 123456789 / '123456789' → 'properties/123456789' を保証 """
    s = str(prop)
    return s if s.startswith("properties/") else f"properties/{s}"

def _ensure_path(url_or_path: str) -> str:
    """ URLでもpathでも受け取り、必ず '/...' の形にする """
    if not url_or_path:
        return "/"
    if url_or_path.startswith("/"):
        return url_or_path or "/"
    try:
        p = urlparse(url_or_path if url_or_path.startswith(("http://","https://")) else "https://" + url_or_path)
        return p.path or "/"
    except Exception:
        return "/"

def fetch_ga_conversion_for_url(
    *,
    creds,            # ★ 追加：ユーザーOAuthの Credentials
    ga_property,      # ★ 追加：'properties/123...' または 数字ID
    start_date: str,
    end_date: str,
    full_url: str
) -> pd.DataFrame:
    """
    指定プロパティで pagePath == full_url のコンバージョンを取得して DataFrame で返す
    返値: DataFrame(columns=['URL','コンバージョン数'])
    """
    property_name = _as_property_str(ga_property)
    path = _ensure_path(full_url)

    client = BetaAnalyticsDataClient(credentials=creds)

    req = RunReportRequest(
        property=property_name,
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="conversions")],
        dimension_filter=FilterExpression(
            filter=Filter(
                field_name="pagePath",
                string_filter=Filter.StringFilter(
                    value=path,
                    match_type=Filter.StringFilter.MatchType.EXACT
                )
            )
        ),
    )

    resp = client.run_report(req)

    rows = []
    for r in getattr(resp, "rows", []):
        rows.append({
            "URL": r.dimension_values[0].value,
            "コンバージョン数": int(r.metric_values[0].value or 0),
        })
    return pd.DataFrame(rows)

def get_domain_from_url(site_url: str) -> str:
    """
    https://www.example.com → https://example.com
    """
    parsed = urlparse(site_url if site_url.startswith(("http://","https://")) else "https://" + site_url)
    return f"https://{parsed.netloc.replace('www.', '')}"
