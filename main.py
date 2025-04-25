
import pandas as pd
from datetime import datetime, timedelta
from serp_api_utils import get_top_competitor_urls, get_meta_info_from_url
from chatgpt_utils import build_prompt, get_chatgpt_response
from ga_utils import fetch_ga_data
from gsc_utils import get_search_console_service, fetch_gsc_data
from sheet_utils import (
    get_spreadsheet,
    get_or_create_worksheet,
    update_sheet,
    write_gsc_data_to_sheet,
    write_ga_data_to_sheet
)

SPREADSHEET_ID = '1Fpdb-3j89j7OkPmJXbdmSmFBaA6yj2ZB0AUBNvF6BQ4'

def process_seo_improvement(site_url):
    print(f"🚀 SEO改善を開始: {site_url}")

    today = datetime.today().date()
    this_week_start = today - timedelta(days=7)
    this_week_end = today
    last_week_start = today - timedelta(days=14)
    last_week_end = today - timedelta(days=7)

    service = get_search_console_service()
    df_this_week = fetch_gsc_data(service, site_url, this_week_start, this_week_end)
    df_last_week = fetch_gsc_data(service, site_url, last_week_start, last_week_end)

    print("last_week rows:", len(df_last_week))
    print("this_week rows:", len(df_this_week))
    print(df_this_week.head())

    spreadsheet = get_spreadsheet(SPREADSHEET_ID)
    sheet_suggestions = get_or_create_worksheet(spreadsheet, "改善案")
    update_sheet(sheet_suggestions, ['URL', 'クリック数', '表示回数', 'CTR（%）', '平均順位'], df_this_week.values.tolist())

    gsc_data_for_export = []
    for _, row in df_this_week.iterrows():
        gsc_data_for_export.append({
            "url": row["URL"],
            "query": "（仮）",
            "position": row["平均順位"],
            "clicks": row["クリック数"],
            "impressions": row["表示回数"]
        })

    merged_df = pd.merge(df_last_week, df_this_week, on='URL', suffixes=('_先週', '_今週'))
    merged_df['順位変化'] = merged_df['平均順位_今週'] - merged_df['平均順位_先週']
    dropped_df = merged_df[merged_df['順位変化'] > 0].sort_values(by='順位変化', ascending=False)

    sheet_dropped = get_or_create_worksheet(spreadsheet, "順位が下がったページ")
    update_sheet(sheet_dropped, ['URL', '平均順位（先週）', '平均順位（今週）', '順位変化'],
                 dropped_df[['URL', '平均順位_先週', '平均順位_今週', '順位変化']].values.tolist())

    if dropped_df.empty:
        print("❌ 順位が下がったページが見つかりませんでした。")

    all_df = pd.merge(df_last_week, df_this_week, on='URL', suffixes=('_先週', '_今週'))
    if all_df.empty:
        print("⚠️ データがまったく存在しないため、改善対象ページを選べません。")
        return "<p>データが不足しているため改善提案を表示できませんでした。</p>"

    worst_page = all_df.sort_values(by='平均順位_今週', ascending=False).iloc[0]
    target_url = worst_page['URL']
    print(f"🎯 対象ページ: {target_url}")

    try:
        meta_info = get_meta_info_from_url(target_url)
        keyword = meta_info.get("title") or meta_info.get("description") or "SEO"
        print(f"🔍 抽出されたキーワード: {keyword}")
    except Exception as e:
        print(f"⚠️ メタ情報の取得に失敗: {e}")
        return

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
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SEO 改善提案</title>
    </head>
    <body>
        <h2>SEO 改善提案</h2>
        <p><strong>対象URL：</strong> {target_url}</p>
        <h3>💡 ChatGPTの改善提案</h3>
        <p>{response}</p>
        <a href="/">戻る</a>
    </body>
    </html>
    """

    with open("templates/result.html", "w", encoding="utf-8") as f:
        f.write(result_html)

    print("✅ HTMLファイルに出力しました。")

    write_gsc_data_to_sheet(spreadsheet, gsc_data_for_export)
    write_ga_data_to_sheet(spreadsheet, fetch_ga_data(this_week_start.isoformat(), this_week_end.isoformat()))

    return result_html

if __name__ == "__main__":
    process_seo_improvement("https://mrseoai.com")
