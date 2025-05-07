from urllib.parse import urlparse
from flask import Flask, request, render_template
from main import process_seo_improvement


app = Flask(__name__)

def to_domain_property(url):
    """http(s)://www.などを sc-domain:ドメイン名 に変換"""
    parsed = urlparse(url)
    domain = parsed.hostname.replace("www.", "") 
    return f"sc-domain:{domain}"

@app.route("/", methods=["GET", "POST"])
def index():
    result = None  # 初期状態では結果なし
    if request.method == "POST":
        input_url = request.form["url"]
        site_url = to_domain_property(input_url) 
        result = process_seo_improvement(site_url)  # ドメインプロパティ形式で渡す
    return render_template("index.html", result_data=result)
@app.route('/result')
def show_result():
    return render_template('result.html', site_url="（前回のURL）", table_html="（前回の表データ）")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)