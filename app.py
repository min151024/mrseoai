from urllib.parse import urlparse
from flask import Flask, redirect, session, url_for, request, render_template
from oauth import create_flow, get_credentials_from_session, store_credentials_in_session
from main import process_seo_improvement
import os

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "defaultsecretkey")  # セッション用

def to_domain_property(url):
    parsed = urlparse(url)
    domain = parsed.hostname.replace("www.", "")
    return f"sc-domain:{domain}"

def is_authenticated():
    return session.get("user_authenticated", False)

def is_oauth_authenticated():
    return "credentials" in session

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # 未登録・未ログインなら登録画面へ
        if not is_authenticated() or not is_oauth_authenticated():
            return redirect(url_for("register"))
        
        # ここからは認証済みユーザー向けの処理
        input_url = request.form["url"]
        site_url = to_domain_property(input_url)
        result = process_seo_improvement(site_url)

        return render_template(
            "result.html",
            site_url=input_url,
            table_html=result["table_html"],
            chart_labels=result["chart_labels"],
            chart_data=result["chart_data"],
            competitors=result["competitors"],
            chatgpt_response=result.get("chatgpt_response", "")
        )

    # GET のときは誰でも index.html を表示
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # Firebase 登録完了
        session["user_authenticated"] = True
        # Google OAuth 開始
        flow = create_flow()
        auth_url, _ = flow.authorization_url(
            prompt="consent",
            access_type="offline",
            include_granted_scopes="true"
        )
        return redirect(auth_url)

    # GET時は登録フォーム＆ログインリンクを表示
    return render_template("register.html",
        FIREBASE_API_KEY=os.getenv("FIREBASE_API_KEY"),
        FIREBASE_AUTH_DOMAIN=os.getenv("FIREBASE_AUTH_DOMAIN"),
        FIREBASE_PROJECT_ID=os.getenv("FIREBASE_PROJECT_ID"),
        FIREBASE_APP_ID=os.getenv("FIREBASE_APP_ID")
    )

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Firebase ログイン成功
        session["user_authenticated"] = True
        # Google OAuth 開始
        flow = create_flow()
        auth_url, _ = flow.authorization_url(
            prompt="consent",
            access_type="offline",
            include_granted_scopes="true"
        )
        return redirect(auth_url)

    # GET時はログインフォーム＆登録リンクを表示
    return render_template("login.html",
        FIREBASE_API_KEY=os.getenv("FIREBASE_API_KEY"),
        FIREBASE_AUTH_DOMAIN=os.getenv("FIREBASE_AUTH_DOMAIN"),
        FIREBASE_PROJECT_ID=os.getenv("FIREBASE_PROJECT_ID"),
        FIREBASE_APP_ID=os.getenv("FIREBASE_APP_ID")
    )

@app.route("/oauth2callback")
def oauth2callback():
    flow = create_flow()
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    store_credentials_in_session(credentials)
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("register"))

@app.route("/result", methods=["GET", "POST"])
def result():
    if request.method == "POST":
        input_url = request.form["url"]
        site_url = to_domain_property(input_url)
        data = process_seo_improvement(site_url)
        return render_template(
            "result.html",
            site_url=input_url,
            table_html=data["table_html"],
            chart_labels=data["chart_labels"],
            chart_data=data["chart_data"],
            competitors=data["competitors"],
            chatgpt_response=data.get("chatgpt_response", "")
        )

    past = session.get("past_improvements", [])
    return render_template("result.html", past_improvements=past)



@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/terms")
def terms():
    return render_template("terms.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
