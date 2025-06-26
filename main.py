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
    update_sheet,
    write_competitor_data_to_sheet
)

SPREADSHEET_ID = '1Fpdb-3j89j7OkPmJXbdmSmFBaA6yj2ZB0AUBNvF6BQ4'

def extract_path_from_url(full_url: str) -> str:
    parsed_url = urlparse(full_url)
    return parsed_url.path or "/"

def process_seo_improvement(site_url, skip_metrics: bool = False):
    print(f"\U0001F680 SEO改善を開始: {site_url}")

    if skip_metrics:
        df_this_week = pd.DataFrame() 
    else:
        today = datetime.today().date()
        yesterday = today - timedelta(days=2)
        this_week_start = yesterday - timedelta(days=6)
        this_week_end   = yesterday

        service = get_search_console_service()
        df_this_week = fetch_gsc_data(service, site_url, this_week_start, this_week_end)


    print("✅ 今週のdf:")
    print(df_this_week)

    if df_this_week.empty:
        print("❌ 今週のGSCデータが空なのでフォールバックモードで処理します。")
        # ➡ 辞書で統一して返す
        return {
            "clicks":      None,
            "impressions": None,
            "ctr":         None,
            "position":    None,
            "conversions": None,
            "table_html":  "<p>今週のGSCデータが空です。サービス紹介文と競合情報を元に改善案を作成します。</p>",
            "chart_labels": [],
            "chart_data":   [],
            "competitors":  [],       
            "chatgpt_response": ""  
        }

    ga_conversion_data = []
    top_urls = []
    competitors_info = []

    for url in df_this_week["URL"].unique():
        page_path = urlparse(url).path or "/"
        ga_df = fetch_ga_conversion_for_url(
            start_date=this_week_start.isoformat(),
            end_date=this_week_end.isoformat(),
            full_url=page_path
        )
        if not ga_df.empty:
            ga_conversion_data.append(ga_df.iloc[0])

    if ga_conversion_data:
        ga_df_combined = pd.DataFrame(ga_conversion_data)
    else:
        ga_df_combined = pd.DataFrame(columns=["URL", "コンバージョン数"])

    merged_df = pd.merge(df_this_week, ga_df_combined, on="URL", how="left")
    merged_df["コンバージョン数"] = merged_df["コンバージョン数"].fillna(0).astype(int)

    print("🔎 merged_df の中身:")
    print(merged_df)

    worst_page = merged_df.sort_values(by='平均順位', ascending=False).iloc[0]
    target_url = worst_page['URL']
    print(f"🎯 今週の中で最下位のページを改善対象に選定: {target_url}")

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
        top_urls = []
        competitors_info = []

    competitor_data = []
    for url in top_urls:
        info = get_meta_info_from_url(url)
        competitor_data.append({
            "URL": url,
            "タイトル": info.get("title", ""),
            "メタディスクリプション": info.get("description", "")
        })


    try:
        prompt = build_prompt(target_url, competitors_info, merged_df)
        response = get_chatgpt_response(prompt)
        print("💡 ChatGPT改善案:", response)
    except Exception as e:
        print(f"⚠️ ChatGPTへのリクエスト失敗: {e}")
        response = "ChatGPT からの改善提案を取得できませんでした。"


    spreadsheet = get_spreadsheet(SPREADSHEET_ID)
    sheet_result = get_or_create_worksheet(spreadsheet, "SEOデータ")

    print("📤 スプレッドシートへの書き込みを開始します")
    update_sheet(sheet_result, merged_df.columns.tolist(), merged_df.values.tolist())
    write_competitor_data_to_sheet(spreadsheet, competitor_data)
    print("✅ スプレッドシートに書き込みました。")
        

    html_rows = ""
    for _, row in merged_df.iterrows():
       html_rows += f"<tr><td>{row['URL']}</td><td>{row['クリック数']}</td><td>{row['表示回数']}</td><td>{row['CTR（%）']}</td><td>{row['平均順位']}</td><td>{row['コンバージョン数']}</td></tr>"

    result_html = f"""
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>SEO データ可視化</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ccc; padding: 8px; text-align: center; }}
            </style>
        </head>
        <body>
            <h2>SEO データ可視化</h2>
            <table>
                <thead>
                    <tr><th>URL</th><th>クリック数</th><th>表示回数</th><th>CTR（%）</th><th>平均順位</th><th>コンバージョン数</th></tr>
                </thead>
                <tbody>
                    {html_rows}
                </tbody>
            </table>

            <canvas id="metricsChart" width="800" height="300"></canvas>
            <script>
                const ctx = document.getElementById('metricsChart').getContext('2d');
                const chart = new Chart(ctx, {{
                    type: 'bar',
                    data: {{
                        labels: {merged_df['URL'].tolist()},
                        datasets: [
                            {{
                                label: 'クリック数',
                                data: {merged_df['クリック数'].tolist()},
                                backgroundColor: 'rgba(54, 162, 235, 0.6)'
                            }},
                            {{
                                label: '表示回数',
                                data: {merged_df['表示回数'].tolist()},
                                backgroundColor: 'rgba(255, 206, 86, 0.6)'
                            }},
                            {{
                                label: 'CTR（%）',
                                data: {merged_df['CTR（%）'].tolist()},
                                backgroundColor: 'rgba(75, 192, 192, 0.6)'
                            }},
                            {{
                                label: '平均順位',
                                data: {merged_df['平均順位'].tolist()},
                                backgroundColor: 'rgba(153, 102, 255, 0.6)'
                            }},
                            {{
                                label: 'コンバージョン数',
                                data: {merged_df['コンバージョン数'].tolist()},
                                backgroundColor: 'rgba(255, 99, 132, 0.6)'
                            }}
                        ]
                    }},
                    options: {{
                        responsive: true,
                        plugins: {{
                            legend: {{ position: 'top' }},
                            title: {{ display: true, text: '各ページのSEO指標比較' }}
                        }},
                        scales: {{
                            y: {{ beginAtZero: true }}
                        }}
                    }}
                }});
            </script>

            <h3>ChatGPTによる改善案</h3>
            <div class="chatgpt-response">
                <pre>{response}</pre>
            </div>
        </body>
        </html>
    """

    with open("templates/result.html", "w", encoding="utf-8") as f:
        f.write(result_html)

    print("✅ HTMLファイルに出力しました（グラフ付き）。")

    return {
    "table_html": html_rows,
    "chart_labels": merged_df["URL"].tolist(),
    "chart_data": merged_df["コンバージョン数"].tolist(),
    "competitors": competitor_data
}

if __name__ == "__main__":
    process_seo_improvement("sc-domain:mrseoai.com")
