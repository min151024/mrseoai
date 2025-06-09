from urllib.parse import urlparse
from flask import Flask, redirect, session, url_for, request, render_template, abort
from oauth import create_flow, get_credentials_from_session, store_credentials_in_session
from main import process_seo_improvement
import firebase_admin
from firebase_admin import credentials, firestore, auth as firebase_auth
from werkzeug.middleware.proxy_fix import ProxyFix
import os
from datetime import datetime
from google.cloud import firestore
#os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1' 

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "defaultsecretkey")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config['PREFERRED_URL_SCHEME'] = 'https'


cred = credentials.Certificate("credentials.json")
firebase_admin.initialize_app(cred)
db = firestore.Client()

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

from flask import Flask, request, render_template, session, redirect, url_for, abort
from datetime import datetime
from oauth import create_flow
from main import process_seo_improvement
# Firestore 初期化済みと仮定
# from firebase_admin import firestore
# db = firestore.client()

@app.route("/result", methods=["GET", "POST"])
def result():
    if not session.get("user_authenticated") or not session.get("uid"):
        return redirect(url_for("register"))

    uid = session["uid"]
    new_item = None

    if request.method == "POST":
        input_url = request.form["url"]
        site_url  = to_domain_property(input_url)
        data      = process_seo_improvement(site_url)

        doc = {
          "uid": uid,
          "input_url": input_url,
          "result": data,
          "timestamp": datetime.utcnow()
        }
        db.collection("improvements").add(doc)

        new_item = {
          "input_url": input_url,
          "result":    data,
          "timestamp": doc["timestamp"]
        }

    history = []
    docs = (
      db.collection("improvements")
        .where("uid", "==", uid)
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .stream()
    )
    for d in docs:
        rec = d.to_dict()
        history.append({
          "input_url": rec["input_url"],
          "timestamp": rec["timestamp"].strftime("%Y-%m-%d %H:%M"),
          "chatgpt_response": rec["result"].get("chatgpt_response", "")
        })

    chart_labels = []
    chart_data   = {}
    if new_item:
        chart_labels = [ new_item["input_url"] ]
        chart_data = {
          "clicks":      [new_item["result"]["clicks"]],
          "impressions": [new_item["result"]["impressions"]],
          "ctr":         [new_item["result"]["ctr"]],
          "position":    [new_item["result"]["position"]],
          "conversions": [new_item["result"].get("conversions", 0)]
        }

    return render_template(
      "result.html",
      new_item=new_item,
      chart_labels=chart_labels,
      chart_data=chart_data,
      history=history
    )


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/terms")
def terms():
    return render_template("terms.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
