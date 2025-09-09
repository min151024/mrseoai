from datetime import date, timedelta
from urllib.parse import urlparse
import pandas as pd

from serp_api_utils import get_top_competitor_urls, get_meta_info_from_url
from chatgpt_utils import build_prompt, get_chatgpt_response

from ga_utils import fetch_ga_conversion_for_url
from gsc_utils import fetch_gsc_data
from sheet_utils import (
    get_spreadsheet, get_or_create_worksheet,
    update_sheet, write_competitor_data_to_sheet
)

# Firestore は firebase_admin で統一（google.cloud と混在させない）
from firebase_admin import firestore as fa_firestore
db = fa_firestore.client()


# ---------------------- ヘルパー ----------------------

def _last_28_days():
    """昨日までの直近28日"""
    ed = date.today() - timedelta(days=1)
    sd = ed - timedelta(days=27)
    return sd.isoformat(), ed.isoformat()

def _path_only(u: str) -> str:
    """URLでもパスでもOK → 先頭が / のパスに正規化"""
    if not u:
        return "/"
    if u.startswith("/"):
        return u or "/"
    p = urlparse(u if u.startswith(("http://", "https://")) else "https://" + u)
    return p.path or "/"

# ---------------------- メイン（新シグネチャ） ----------------------

def process_seo_improvement(
    *,
    url: str,                      # フォームで入力されたフルURL（表示用）
    creds=None,                    # ユーザーOAuth Credentials（無ければ None）
    sc_property: str | None = None,# "sc-domain:example.com" or "https://example.com/"
    ga_property: str | int | None = None,   # "properties/123..." or 123 or None
    sheet_id: str | None = None,   # 出力先スプレッドシート（任意）
    skip_metrics: bool = False,    # True なら GA/GSC/Sheets を丸ごとスキップ
) -> dict:
    print(f"🚀 SEO改善を開始: {url} (skip_metrics={skip_metrics})")

    # ---------------- 1) GSC / GA 指標の収集 ----------------
    gsc_df = pd.DataFrame()
    merged_df = pd.DataFrame()
    chart_labels, chart_data = [], {}
    clicks = impressions = conversions = 0
    ctr = position = 0.0

    if not skip_metrics and creds:
        sd, ed = _last_28_days()

        # ---- GSC ----
        if sc_property:
            try:
                raw = fetch_gsc_data(
                    creds=creds,
                    sc_property=sc_property,
                    start_date=sd,
                    end_date=ed,
                    row_limit=25000,
                )  # 列: ['検索キーワード','URL','クリック数','表示回数','CTR（%）','平均順位']
                # URL単位に集計（重複ページがあるため）
                if not raw.empty:
                    gsc_df = (
                        raw.groupby("URL", as_index=False)
                           .agg({
                               "クリック数": "sum",
                               "表示回数": "sum",
                               "CTR（%）": "mean",
                               "平均順位": "mean",
                           })
                    )
            except Exception as e:
                print("GSC取得スキップ:", e)

        # ---- GA（コンバージョン例）----
        ga_conv = pd.DataFrame(columns=["URL", "コンバージョン数"])
        if ga_property and not gsc_df.empty:
            per_url = []
            for u in gsc_df["URL"].unique():
                try:
                    ga_df = fetch_ga_conversion_for_url(
                        creds=creds,
                        ga_property=ga_property,
                        start_date=sd,
                        end_date=ed,
                        full_url=_path_only(u),
                    )  # 列: ['URL','コンバージョン数']
                    if not ga_df.empty:
                        per_url.append(ga_df.iloc[0])
                except Exception as e:
                    print("GA取得スキップ(単ページ):", u, e)
            if per_url:
                ga_conv = pd.DataFrame(per_url)
            else:
                ga_conv = pd.DataFrame(columns=["URL", "コンバージョン数"])

        # ---- マージ ----
        if not gsc_df.empty:
            merged_df = pd.merge(gsc_df, ga_conv, on="URL", how="left")
            merged_df["コンバージョン数"] = merged_df["コンバージョン数"].fillna(0).astype(int)

            # チャート・集計
            chart_labels = merged_df["URL"].tolist()
            chart_data = {
                "clicks":      merged_df["クリック数"].astype(int).tolist(),
                "impressions": merged_df["表示回数"].astype(int).tolist(),
                "ctr":         merged_df["CTR（%）"].astype(float).round(2).tolist(),
                "position":    merged_df["平均順位"].astype(float).round(2).tolist(),
                "conversions": merged_df["コンバージョン数"].astype(int).tolist(),
            }

            clicks       = int(merged_df["クリック数"].sum())
            impressions  = int(merged_df["表示回数"].sum())
            conversions  = int(merged_df["コンバージョン数"].sum())
            ctr          = float(merged_df["CTR（%）"].mean())
            position     = float(merged_df["平均順位"].mean())

    # ---------------- 2) 競合取得 & ChatGPT 提案 ----------------
    # GSCキーワード（あれば）から代表をピックアップ
    gsc_keywords = []
    try:
        if not skip_metrics and "検索キーワード" in locals().get("raw", pd.DataFrame()).columns:
            gsc_keywords = [
                str(k).strip() for k in raw["検索キーワード"].dropna().tolist()
                if str(k).strip()
            ]
    except Exception:
        pass

    competitors_info = []
    competitor_data  = []
    response         = ""  # 生成失敗時は空のまま

    if gsc_keywords:
        try:
            top_urls = get_top_competitor_urls(gsc_keywords[0]) or []
        except Exception as e:
            print("SerpAPI呼び出し失敗:", e)
            top_urls = []

        for idx, u in enumerate(top_urls, start=1):
            try:
                info = get_meta_info_from_url(u)
            except Exception:
                info = {}
            competitors_info.append(info)
            competitor_data.append({
                "URL": u,
                "タイトル": info.get("title", ""),
                "メタディスクリプション": info.get("description", ""),
                "position": idx,
                "title": info.get("title", ""),
                "url": u,
            })

        if competitors_info:
            try:
                prompt = build_prompt(
                    # 改善対象：順位が悪いURL。なければフォームURLのルート。
                    (merged_df.sort_values("平均順位", ascending=False).iloc[0]["URL"]
                     if not merged_df.empty else url.rstrip("/") + "/"),
                    competitors_info,
                    merged_df if not merged_df.empty else pd.DataFrame(),
                )
                response = get_chatgpt_response(prompt) or ""
            except Exception as e:
                print("ChatGPT生成失敗:", e)

    # ---------------- 3) Sheets 書き込み（任意） ----------------
    if (not skip_metrics) and creds and sheet_id:
        try:
            spreadsheet = get_spreadsheet(creds, sheet_id)
            ws = get_or_create_worksheet(spreadsheet, "SEOデータ")

            if not merged_df.empty:
                headers = ["URL", "クリック数", "表示回数", "CTR（%）", "平均順位", "コンバージョン数"]
                rows = merged_df[headers].values.tolist()
            else:
                headers = ["URL", "クリック数", "表示回数", "CTR（%）", "平均順位", "コンバージョン数"]
                rows = []

            update_sheet(ws, headers, rows)
            write_competitor_data_to_sheet(spreadsheet, competitor_data)
            print("✅ Sheets 書き込み完了")
        except Exception as e:
            print("Sheets書き込みスキップ:", e)

    # ---------------- 4) テーブルHTML ----------------
    if not merged_df.empty:
        table_html = merged_df.to_html(classes="table table-sm", index=False)
    else:
        table_html = "<p>直近28日で有効なGSC/GAデータがありませんでした。</p>"

    # ---------------- 5) レスポンス ----------------
    return {
        "clicks":           clicks,
        "impressions":      impressions,
        "ctr":              ctr,
        "position":         position,
        "conversions":      conversions,
        "table_html":       table_html,
        "chart_labels":     chart_labels,
        "chart_data":       chart_data,
        "competitors":      competitor_data,
        "chatgpt_response": response or "",
    }


def get_history_for_user(uid: str):
    """ユーザーの履歴（新しい順）"""
    docs = (
        db.collection("improvements")
          .where("uid", "==", uid)
          .order_by("timestamp", direction=fa_firestore.Query.DESCENDING)
          .stream()
    )
    history = []
    for doc in docs:
        d = doc.to_dict()
        ts = d.get("timestamp")
        if hasattr(ts, "strftime"):
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
        else:
            ts_str = str(ts)
        history.append({
            "id":               doc.id,
            "timestamp":        ts_str,
            "input_url":        d.get("input_url", ""),
            "chatgpt_response": d.get("result", {}).get("chatgpt_response", ""),
        })
    return history


if __name__ == "__main__":
    process_seo_improvement("sc-domain:mrseoai.com")
