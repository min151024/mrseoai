import prepare_credentials
from flask import Flask, request, render_template
from main import process_seo_improvement
import os

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    result = None  # 初期状態では結果なし
    if request.method == "POST":
        target_url = request.form["url"]
        result = process_seo_improvement(target_url)  # ChatGPTの回答を取得
    return render_template("index.html", result=result)  # 結果を渡す

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)