from urllib.parse import urlparse
from flask import Flask, redirect, session, url_for, request, render_template, abort
from oauth import create_flow, get_credentials_from_session, store_credentials_in_session
from main import process_seo_improvement
import firebase_admin
from firebase_admin import credentials, firestore
from firebase_admin import auth as firebase_auth
from werkzeug.middleware.proxy_fix import ProxyFix
import os
from datetime import datetime
from google.cloud import firestore
#os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1' 

cred = credentials.Certificate("credentials.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "defaultsecretkey")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config['PREFERRED_URL_SCHEME'] = 'https'

def to_domain_property(url):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    hostname = parsed.hostname
    if hostname is None:
        abort(400, "URLが不正です。https://example.com のように入力してください。")

    domain = hostname.replace("www.", "")
    return f"sc-domain:{domain}"

def is_authenticated():
    return session.get("user_authenticated", False)

def is_oauth_authenticated():
    return "credentials" in session

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if not is_authenticated() or not is_oauth_authenticated(): #登録していない人は新規登録画面に飛ばされる（登録してから使ってね等のメッセージ必要）
           return redirect(url_for("register"))
        
        input_url = request.form["url"]
        site_url = to_domain_property(input_url)
        result = process_seo_improvement(site_url)

        chart_labels = [ input_url ]
        chart_data = {
        "clicks":      [ result["clicks"] ],
        "impressions": [ result["impressions"] ],
        "ctr":         [ result["ctr"] ],
        "position":    [ result["position"] ],
        "conversions": [ result.get("conversions", 0) ]
        }

        uid = session["uid"]
        doc = {
            "uid": uid,
            "input_url": input_url,
            "result": result,               
            "timestamp": datetime.utcnow()
        }
        db.collection("improvements").add(doc)

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
        firebase_user = firebase_auth.get_user_by_email(request.form["email"])
        session["uid"] = firebase_user.uid
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
        firebase_user = firebase_auth.get_user_by_email(request.form["email"])
        session["uid"] = firebase_user.uid
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

@app.route("/history")
def history():
    if not is_authenticated() or "uid" not in session:
        return redirect(url_for("login"))

    uid = session["uid"]
    # uid フィルタ＋降順ソート
    docs = db.collection("improvements")\
             .where("uid", "==", uid)\
             .order_by("timestamp", direction=firestore.Query.DESCENDING)\
             .stream()

    history = []
    for d in docs:
        data = d.to_dict()
        history.append({
            "input_url": data["input_url"],
            "timestamp": data["timestamp"].strftime("%Y-%m-%d %H:%M"),
            "result": data["result"]          # 必要なサブフィールドだけ取り出してもOK
        })

    return render_template("history.html", history=history)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
