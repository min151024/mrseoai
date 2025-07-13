from urllib.parse import urlparse
from flask import Flask, flash, jsonify, redirect, session, url_for, request, render_template, abort
from oauth import create_flow, store_credentials_in_session
from main import process_seo_improvement, get_history_for_user
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
    uid = session.get("uid")
    history = get_history_for_user(uid) if uid else []

    if request.method == "POST":
        skip_metrics = request.form.get("skip_metrics") == "on"
        effective_skip  = skip_metrics
        history = get_history_for_user(uid)

        # スキップ指定がない場合のみ認証チェック
        if not skip_metrics:
            if not is_authenticated():
                flash("まずはログインしてください")
                return redirect(url_for("login"))
            oauth_ready = is_oauth_authenticated()
            if not oauth_ready:
                flash("GA/GSC連携がありません。スキップモードで分析します。")
                effective_skip = True

            user_skip = request.form.get("skip_metrics") == "on"
            # OAuth未連携でも分析したい場合は強制フォールバック
            effective_skip = user_skip or not oauth_ready

            # ③ OAuthが済んでいない & ユーザーが明示的に連携希望しないときは注意を出す
            if not user_skip and not oauth_ready:
                flash("Google Analytics/Search Console 連携がありません。データ連携なしモードで分析します。")


        input_url = request.form["url"]
        site_url  = to_domain_property(input_url)
        result = process_seo_improvement(site_url, skip_metrics=effective_skip)

        if uid:
            doc = {
                "uid":            uid,
                "input_url":      input_url,
                "result":         result,
                "timestamp":      datetime.utcnow()
            }
            db.collection("improvements").add(doc)
            # 追加後、再取得して最新順にする
            history = get_history_for_user(uid)


        return render_template(
            "result.html",
            site_url=input_url,
            table_html=result["table_html"],
            chart_labels=result["chart_labels"],
            chart_data=result["chart_data"],
            competitors=result["competitors"],
            chatgpt_response=result.get("chatgpt_response", ""),
            history=history
        )

    # GET のときは誰でも index.html を表示
    return render_template("index.html", history=history)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # JSON ボディから ID トークンを取り出す
        body = request.get_json(silent=True)
        if not body or "idToken" not in body:
            abort(400, "idToken がありません")

        # Firebase Admin SDK でトークンを検証し、UID を取得
        try:
            decoded = firebase_auth.verify_id_token(body["idToken"])
        except Exception as e:
            abort(400, f"トークンの検証に失敗しました: {e}")

        session["user_authenticated"] = True
        session["uid"] = decoded["uid"]

        # そのまま Google OAuth フロー開始
        flow = create_flow()
        auth_url, _ = flow.authorization_url(
            prompt="consent",
            access_type="offline",
            include_granted_scopes="true"
        )
        return jsonify({ "auth_url": auth_url })

    # GET時は クライアント登録フォーム を表示
    return render_template("register.html",
        FIREBASE_API_KEY=os.getenv("FIREBASE_API_KEY"),
        FIREBASE_AUTH_DOMAIN=os.getenv("FIREBASE_AUTH_DOMAIN"),
        FIREBASE_PROJECT_ID=os.getenv("FIREBASE_PROJECT_ID"),
        FIREBASE_APP_ID=os.getenv("FIREBASE_APP_ID")
    )

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        # register と同様に firebaseConfig を渡す
        return render_template("login.html",
            FIREBASE_API_KEY     = os.getenv("FIREBASE_API_KEY"),
            FIREBASE_AUTH_DOMAIN = os.getenv("FIREBASE_AUTH_DOMAIN"),
            FIREBASE_PROJECT_ID  = os.getenv("FIREBASE_PROJECT_ID"),
            FIREBASE_APP_ID      = os.getenv("FIREBASE_APP_ID")
        )

    # POST(JSON) で来たら ID トークン検証
    body = request.get_json(silent=True)
    if not body or "idToken" not in body:
        abort(400, "idToken がありません")

    try:
        decoded = firebase_auth.verify_id_token(body["idToken"])
    except Exception as e:
        abort(400, f"トークン検証に失敗: {e}")

    session["user_authenticated"] = True
    session["uid"] = decoded["uid"]

    return jsonify({ "status": "ok" })

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
    # 認証チェック
    if not session.get("user_authenticated") or not session.get("uid"):
        return redirect(url_for("login"))

    uid = session["uid"]

    # POST/GET 共通で使う変数を先に初期化
    new_item = None
    chart_labels = []
    chart_data   = {}
    raw_competitors = []
    competitors     = []
    history         = []

    # --- 新規分析処理（フォーム送信時のみ） ---
    if request.method == "POST":
        input_url = request.form["url"]
        site_url  = to_domain_property(input_url)
        data      = process_seo_improvement(site_url)

        # 取得した競合リストを保持
        raw_competitors = data.get("competitors", [])

        # Firestore に永続化
        timestamp = datetime.utcnow()
        db.collection("improvements").add({
            "uid": uid,
            "input_url": input_url,
            "result": data,
            "timestamp": timestamp
        })

        # 新規アイテム用データ
        new_item = {
            "input_url": input_url,
            "result":    data,
            "timestamp": timestamp
        }

        # グラフ用ラベル＆データ
        chart_labels = [input_url]
        chart_data = {
            "clicks":      [data.get("clicks", 0)],
            "impressions": [data.get("impressions", 0)],
            "ctr":         [data.get("ctr", 0)],
            "position":    [data.get("position", 0)],
            "conversions": [data.get("conversions", 0)]
        }

        # 競合リストをテンプレート向けにフォーマット
        for comp in raw_competitors:
            competitors.append({
                "position": comp.get("position") or comp.get("rank"),
                "title":    comp.get("title")    or comp.get("page_title"),
                "url":      comp.get("url")      or comp.get("link")
            })

    # --- 履歴取得（常に実行） ---
    docs = (
        db.collection("improvements")
          .where("uid", "==", uid)
          .order_by("timestamp", direction=firestore.Query.DESCENDING)
          .stream()
    )
    for d in docs:
        rec = d.to_dict()
        history.append({
            "input_url":        rec.get("input_url"),
            "timestamp":        rec.get("timestamp").strftime("%Y-%m-%d %H:%M"),
            "chatgpt_response": rec.get("result", {}).get("chatgpt_response", "")
        })

    return render_template(
        "result.html",
        new_item=new_item,
        chart_labels=chart_labels,
        chart_data=chart_data,
        competitors=competitors,
        history=history
    )

@app.route("/delete_improvement", methods=["POST"])
def delete_improvement():
    doc_id = request.form.get("doc_id")
    try:
        db.collection("improvements").document(doc_id).delete()
        flash("改善提案を削除しました", "success")
    except Exception as e:
        flash(f"削除に失敗しました: {e}", "error")
    # 元の一覧に戻る
    return redirect(request.referrer or url_for("index"))


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/terms")
def terms():
    return render_template("terms.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
