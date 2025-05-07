from urllib.parse import urlparse
from flask import Flask, request, render_template, redirect, url_for
from main import process_seo_improvement
import os

app = Flask(__name__)

# フォームで入力されたURLを GSCのドメインプロパティ形式に変換
def to_domain_property(url):
    parsed = urlparse(url)
    domain = parsed.hostname.replace("www.", "")
    return f"sc-domain:{domain}"

# 分析フォームのトップページ
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        input_url = request.form["url"]
        site_url = to_domain_property(input_url)
        result = process_seo_improvement(site_url)

        return render_template(
            "result.html",
            table_html=result["table_html"],
            chart_labels=result["chart_labels"],
            chart_data=result["chart_data"],
            competitors=result["competitors"]
        )

    return render_template("index.html")

# 過去の改善結果ページ（仮の実装）
@app.route("/result")
def show_result():
    return render_template("result.html", table_html="", chart_labels=[], chart_data=[], competitors=[])


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)