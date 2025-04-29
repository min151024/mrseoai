import pandas as pd
from datetime import datetime, timedelta
from urllib.parse import urlparse
from serp_api_utils import get_top_competitor_urls, get_meta_info_from_url
from chatgpt_utils import build_prompt, get_chatgpt_response
from ga_utils import fetch_ga_conversion_for_url
from gsc_utils import get_search_console_service, fetch_gsc_data
from sheet_utils import (
    get_spreadsheet,
    get_or_create_worksheet,
    update_sheet
)

SPREADSHEET_ID = '1Fpdb-3j89j7OkPmJXbdmSmFBaA6yj2ZB0AUBNvF6BQ4'

def extract_path_from_url(full_url: str) -> str:
    parsed_url = urlparse(full_url)
    return parsed_url.path or "/"

def process_seo_improvement(site_url):
    print(f"\U0001F680 SEO改善を開始: {site_url}")

    today = datetime.today().date()
    yesterday = today - timedelta(days=1)

    this_week_start = yesterday - timedelta(days=6)
    this_week_end = yesterday

    last_week_start = yesterday - timedelta(days=13)
    last_week_end = yesterday - timedelta(days=7)

    service = get_search_console_service()
    df_this_week = fetch_gsc_data(service, site_url, this_week_start, this_week_end)
    df_last_week = fetch_gsc_data(service, site_url, last_week_start, last_week_end)

    if df_this_week.empty:
        print("⚠️ 今週のGSCデータが空です。")
        return "<p>データが不足しているため改善提案を表示できませんでした。</p>"

    ga_conversion_data = []
    for url in df_this_week["URL"].unique():
        ga_df = fetch_ga_conversion_for_url(
            start_date=this_week_start.isoformat(),
            end_date=this_week_end.isoformat(),
            full_url=url
        )
        if not ga_df.empty:
            ga_conversion_data.append(ga_df.iloc[0])

    if ga_conversion_data:
        ga_df_combined = pd.DataFrame(ga_conversion_data)
    else:
        ga_df_combined = pd.DataFrame(columns=["URL", "コンバージョン数"])

    merged_df = pd.merge(df_this_week, ga_df_combined, on="URL", how="left")
    merged_df["コンバージョン数"] = merged_df["コンバージョン数"].fillna(0).astype(int)

    spreadsheet = get_spreadsheet(SPREADSHEET_ID)
    sheet_result = get_or_create_worksheet(spreadsheet, "SEOデータ")
    update_sheet(sheet_result, merged_df.columns.tolist(), merged_df.values.tolist())

    print("✅ スプレッドシートに書き込みました。")

    merged_compare = pd.merge(df_last_week, df_this_week, on='URL', suffixes=('_先週', '_今週'))
    merged_compare['順位変化'] = merged_compare['平均順位_今週'] - merged_compare['平均順位_先週']
    dropped_df = merged_compare[merged_compare['順位変化'] > 0].sort_values(by='順位変化', ascending=False)

    if dropped_df.empty:
        print("❌ 順位が下がったページが見つかりませんでした。")
        return "<p>順位が下がったページが見つかりませんでした。</p>"

    worst_page = dropped_df.iloc[0]
    target_url = worst_page['URL']
    print(f"🎯 対象ページ: {target_url}")

    try:
        meta_info = get_meta_info_from_url(target_url)
        keyword = meta_info.get("title") or meta_info.get("description") or "SEO"
        print(f"🔍 抽出されたキーワード: {keyword}")
    except Exception as e:
        print(f"⚠️ メタ情報の取得に失敗: {e}")
        keyword = "SEO"

    try:
        top_urls = get_top_competitor_urls(keyword)
        competitors_info = [get_meta_info_from_url(url) for url in top_urls if url]
    except Exception as e:
        print(f"⚠️ 競合ページの取得に失敗: {e}")
        competitors_info = []

    try:
        prompt = build_prompt(target_url, competitors_info)
        response = get_chatgpt_response(prompt)
        print("💡 ChatGPT改善案:", response)
    except Exception as e:
        print(f"⚠️ ChatGPTへのリクエスト失敗: {e}")
        response = "ChatGPT からの改善提案を取得できませんでした。"

    result_html = f"""
    <!DOCTYPE html>
    <html lang=\"ja\">
    <head>
        <meta charset=\"UTF-8\">
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
        <title>SEO 改善提案</title>
    </head>
    <body>
        <h2>SEO 改善提案</h2>
        <p><strong>対象URL：</strong> {target_url}</p>
        <h3>💡 ChatGPTの改善提案</h3>
        <p>{response}</p>
        <a href=\"/\">戻る</a>
    </body>
    </html>
    """

    with open("templates/result.html", "w", encoding="utf-8") as f:
        f.write(result_html)

    print("✅ HTMLファイルに出力しました。")

    return result_html

if __name__ == "__main__":
    process_seo_improvement("sc-domain:mrseoai.com")