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
)
from google.cloud import firestore
db = firestore.Client()


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

    clicks       = 0
    impressions  = 0
    ctr          = 0.0
    position     = 0
    conversions  = 0
    table_html   = ""
    chart_labels = []
    chart_data   = []
    merged_df    = pd.DataFrame() 

    if df_this_week.empty:
        print("❌ 今週のGSCデータが空なのでフォールバックモードで処理します。")
        table_html = "<p>今週のGSC/GAデータが空です。サービス紹介文と競合情報を元に改善案を作成します。</p>"

    else:
        ga_conversion_data = []
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
            ga_df_combined = pd.DataFrame(columns=["URL", "conversions"])

        merged_df = pd.merge(df_this_week, ga_df_combined, on="URL", how="left")
        merged_df["conversions"] = merged_df["conversions"].fillna(0).astype(int)

        print("🔎 merged_df の中身:")
        print(merged_df)

        # —– メトリクス集計 —–
        clicks      = int(merged_df['clicks'].sum())
        impressions = int(merged_df['impressions'].sum())
        ctr         = float(merged_df['ctr'].mean())
        position    = float(merged_df['position'].mean())
        conversions = int(merged_df['conversions'].sum())

        # —– チャート用データ & テーブルHTML —–
        chart_labels = merged_df["URL"].tolist()
        chart_data = {
            "clicks":      merged_df["clicks"].tolist(),
            "impressions": merged_df["impressions"].tolist(),
            "ctr":         merged_df["ctr"].tolist(),
            "position":    merged_df["position"].tolist(),
            "conversions": merged_df["conversions"].tolist()
        }
        table_html   = merged_df.to_html(classes="table table-sm", index=False)

    # 3. ターゲットURL選定（merged_df が空ならサイトTOP）
    if not merged_df.empty:
        worst_page = merged_df.sort_values(by='position', ascending=False).iloc[0]
        target_url = worst_page['URL']
    else:
        target_url = site_url.rstrip("/") + "/"
    print(f"🎯 改善対象ページ: {target_url}")

    # 4. 競合情報取得 & ChatGPT 改善案呼び出し（共通）
    try:
        meta_info = get_meta_info_from_url(target_url)
        keyword   = meta_info.get("title") or meta_info.get("description") or "SEO"
    except:
        keyword = "SEO"  #これどういうこと

    try:
        top_urls         = get_top_competitor_urls(keyword)
        competitors_info = [get_meta_info_from_url(u) for u in top_urls if u]
    except:
        competitors_info = []

    competitor_data = []
    for idx, u in enumerate(top_urls, start=1):
        info = get_meta_info_from_url(u)
        competitor_data.append({
            "メタディスクリプション": idx,
            "タイトル":    info.get("title",""),
            "URL":      u
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

    update_sheet(sheet_result, merged_df.columns.tolist(), merged_df.values.tolist())
        

    html_rows = ""
    for _, row in merged_df.iterrows():
       html_rows += f"<tr><td>{row['URL']}</td><td>{row['clicks']}</td><td>{row['impressions']}</td><td>{row['ctr']}</td><td>{row['position']}</td><td>{row['conversions']}</td></tr>"

    total_clicks = merged_df['clicks'].sum()
    total_impressions = merged_df['impressions'].sum()
    overall_ctr = (total_clicks / total_impressions) * 100 if total_impressions > 0 else 0
    average_position = merged_df['position'].mean()
    total_conversions = merged_df['conversions'].sum()

    clicks      = int(total_clicks)
    impressions = int(total_impressions)
    ctr         = float(overall_ctr)
    position    = float(average_position)
    conversions = int(total_conversions)
    table_html   = html_rows
    chart_labels = merged_df["URL"].tolist()
    data = {
        "clicks":      merged_df["clicks"].tolist(),
        "impressions": merged_df["impressions"].tolist(),
        "ctr":         merged_df["ctr"].tolist(),
        "position":    merged_df["position"].tolist(),
        "conversions": merged_df["conversions"].tolist()
    }

    return {
        "clicks":           clicks,
        "impressions":      impressions,
        "ctr":              ctr,
        "position":         position,
        "conversions":      conversions,
        "table_html":       table_html,
        "chart_labels":     chart_labels,
        "chart_data":       data,
        "competitors":      competitor_data,
        "chatgpt_response": response or ""
    }

def get_history_for_user(uid):
    docs = (
        db.collection("improvements")
          .where("uid", "==", uid)
          .order_by("timestamp", direction=firestore.Query.DESCENDING)
          .stream()
    )
    history = []
    for doc in docs:
        d = doc.to_dict()
        history.append({
            "id":               doc.id,
            "timestamp":        d["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
            "input_url":        d["input_url"],
            "chatgpt_response": d["result"]["chatgpt_response"]
        })
    return history

if __name__ == "__main__":
    process_seo_improvement("sc-domain:mrseoai.com")
