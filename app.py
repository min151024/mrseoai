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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
