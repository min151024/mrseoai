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
        merged_df = pd.DataFrame(columns=[
        "URL", "クリック数", "表示回数", "CTR（%）", "平均順位", "コンバージョン数"
        ])
        table_html = "<p>今週のGSC/GAデータが空です…</p>"

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
            ga_df_combined = pd.DataFrame(columns=["URL", "コンバージョン数"])

        merged_df = pd.merge(df_this_week, ga_df_combined, on="URL", how="left")
        merged_df["コンバージョン数"] = merged_df["コンバージョン数"].fillna(0).astype(int)

        print("🔎 merged_df の中身:")
        print(merged_df)

        if merged_df.empty:
            clicks = 0
            impressions = 0
            ctr = 0
            position = 0
            conversions = 0
        else:
            clicks      = int(merged_df['クリック数'].sum())
            impressions = int(merged_df['表示回数'].sum())
            ctr         = float(merged_df['CTR（%）'].mean())
            position    = float(merged_df['平均順位'].mean())
            conversions = int(merged_df['コンバージョン数'].sum())

        # —– チャート用データ & テーブルHTML —–
        chart_labels = merged_df["URL"].tolist()
        chart_data = {
            "clicks":      merged_df["クリック数"].tolist(),
            "impressions": merged_df["表示回数"].tolist(),
            "ctr":         merged_df["CTR（%）"].tolist(),
            "position":    merged_df["平均順位"].tolist(),
            "conversions": merged_df["コンバージョン数"].tolist()
        }
        table_html   = merged_df.to_html(classes="table table-sm", index=False)

    # 3. ターゲットURL選定（merged_df が空ならサイトTOP）
    if not merged_df.empty:
        worst_page = merged_df.sort_values(by='平均順位', ascending=False).iloc[0]
        target_url = worst_page['URL']
    else:
        target_url = site_url.rstrip("/") + "/"
    print(f"🎯 改善対象ページ: {target_url}")

        # 4. 競合情報取得 & ChatGPT 改善案呼び出し（GSCキーワードがある時だけ）
    # --- GSCの「クエリ」列がある場合のみキーワードとして利用 ---
    gsc_keywords = []
    if (not df_this_week.empty) and ("クエリ" in df_this_week.columns):
        gsc_keywords = [str(k).strip() for k in df_this_week["クエリ"].dropna().tolist() if str(k).strip()]

    competitors_info = []
    competitor_data  = []
    response         = ""   # ← デフォルトは「生成しない」

    if gsc_keywords:  # ← ★キーワードが1つも無ければ SERP/ChatGPT はスキップ
        # 代表キーワード1つでSERP（必要なら上位N件などに拡張）
        top_urls = []
        try:
            top_urls = get_top_competitor_urls(gsc_keywords[0])
        except Exception as e:
            print(f"⚠️ SerpAPI呼び出し失敗: {e}")
            top_urls = []

        if top_urls:
            # 競合ページのタイトル/ディスクリプションを取得
            for idx, u in enumerate(top_urls, start=1):
                info = get_meta_info_from_url(u)
                competitors_info.append(info)
                competitor_data.append({
                    "URL": u,
                    "タイトル": info.get("title", ""),
                    "メタディスクリプション": info.get("description", ""),
                    "position": idx,
                    "title": info.get("title", ""),
                    "url": u
                })

            # 競合が取れた時だけChatGPT
            try:
                prompt = build_prompt(target_url, competitors_info, merged_df)
                response = get_chatgpt_response(prompt)
                print("💡 ChatGPT改善案:", response)
            except Exception as e:
                print(f"⚠️ ChatGPTへのリクエスト失敗: {e}")
                response = ""  # 失敗時も空のまま
        else:
            print("ℹ️ 競合URLが取得できず、ChatGPT生成はスキップしました。")
    else:
        print("ℹ️ GSCキーワードが無いため、SERP/ChatGPTをスキップします。")


    spreadsheet = get_spreadsheet(SPREADSHEET_ID)
    sheet_result = get_or_create_worksheet(spreadsheet, "SEOデータ")

    print("📤 スプレッドシートへの書き込みを開始します")
    update_sheet(sheet_result, merged_df.columns.tolist(), merged_df.values.tolist())
    write_competitor_data_to_sheet(spreadsheet, competitor_data)
    print("✅ スプレッドシートに書き込みました。")
        

    html_rows = ""
    for _, row in merged_df.iterrows():
       html_rows += f"<tr><td>{row['URL']}</td><td>{row['クリック数']}</td><td>{row['表示回数']}</td><td>{row['CTR（%）']}</td><td>{row['平均順位']}</td><td>{row['コンバージョン数']}</td></tr>"

    total_clicks = merged_df['クリック数'].sum()
    total_impressions = merged_df['表示回数'].sum()
    overall_ctr = (total_clicks / total_impressions) * 100 if total_impressions > 0 else 0
    average_position = merged_df['平均順位'].mean()
    total_conversions = merged_df['コンバージョン数'].sum()

    clicks      = int(total_clicks)
    impressions = int(total_impressions)
    ctr         = float(overall_ctr)
    position    = float(average_position)
    conversions = int(total_conversions)
    table_html   = html_rows
    chart_labels = merged_df["URL"].tolist()
    data = {
        "clicks":      merged_df["クリック数"].tolist(),
        "impressions": merged_df["表示回数"].tolist(),
        "ctr":         merged_df["CTR（%）"].tolist(),
        "position":    merged_df["平均順位"].tolist(),
        "conversions": merged_df["コンバージョン数"].tolist()
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
