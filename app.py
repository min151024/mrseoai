from urllib.parse import urlparse, urlunparse
from flask import Flask, flash, jsonify, redirect, session, url_for, request, render_template, abort
from oauth import create_flow, store_credentials_in_session
from main import process_seo_improvement, get_history_for_user
import firebase_admin
from firebase_admin import firestore as fa_firestore, auth as firebase_auth
from oauth import exchange_code_and_store, get_user_credentials
from werkzeug.middleware.proxy_fix import ProxyFix
import os
from datetime import datetime
#os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1' 

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "defaultsecretkey")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config['PREFERRED_URL_SCHEME'] = 'https'


#cred = credentials.Certificate("credentials.json")
#firebase_admin.initialize_app(cred)
try:
    firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app()
db = fa_firestore.client()

def to_sc_property(raw_url: str) -> str:
    """
    入力URLをSearch Consoleの siteUrl 形式（例: https://example.com/）に正規化する。
    - スキームが無ければ https:// を付与
    - パス等は捨ててオリジン（スキーム + ホスト + 末尾スラッシュ）に丸める
    - 日本語ドメインや大文字等も想定
    例:
      "example.com/blog?a=b" -> "https://example.com/"
      "http://EXAMPLE.com"  -> "http://example.com/"
    """
    url = raw_url.strip()

    # 空ならエラー
    if not url:
        raise ValueError("URLが空です。")

    # スキームが無ければ https:// を前置
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # 解析
    p = urlparse(url)

    # netloc（ホスト部）が無いのは不正
    if not p.netloc:
        raise ValueError(f"URLが不正です: {raw_url}")

    # ホストは小文字に
    netloc = p.netloc.lower()

    # オリジン + 末尾スラッシュ に統一（Search Console siteUrl 形式）
    normalized = urlunparse((p.scheme, netloc, "/", "", "", ""))

    return normalized

def is_authenticated():
    return session.get("user_authenticated", False)

def is_oauth_authenticated():
    uid = session.get("uid")
    if not uid:
        return False
    # Firestore に保存済みのトークンがあれば True
    return get_user_credentials(uid) is not None

def _to_site_root(u: str) -> str:
    if not u.startswith(("http://","https://")):
        u = "https://" + u
    p = urlparse(u)
    return f"{p.scheme}://{p.netloc}"

def _site_key(root: str) -> str:
    return root.replace("https://","").replace("http://","").strip("/")

def load_site_config(uid: str | None, input_url: str):
    """
    Firestore に sites/{uid}/owned/{siteKey} があればそれを使い、
    無ければ to_sc_property で推定した値を返す（暫定フォールバック）。
    """
    root = _to_site_root(input_url)
    sc_prop = to_sc_property(root)  # 既定の推定
    ga_prop = None
    sheet_id = None

    if uid:
        doc = (
            db.collection("sites").document(uid)
              .collection("owned").document(_site_key(root)).get()
        )
        if doc.exists:
            cfg = doc.to_dict() or {}
            sc_prop = cfg.get("sc_property") or sc_prop
            ga_prop = cfg.get("ga_property_id")  # "properties/123..." 推奨
            sheet_id = cfg.get("sheet_id")

    return root, sc_prop, ga_prop, sheet_id

def load_history_from_db(uid):
    """Firestore から当該ユーザーの履歴を降順で取得してリスト化"""
    history = []
    docs = (
        db.collection("improvements")
          .where("uid", "==", uid)
          .order_by("timestamp", direction=fa_firestore.Query.DESCENDING)
          .stream()
    )
    for d in docs:
        rec = d.to_dict()
        history.append({
            "id":               d.id,
            "input_url":        rec.get("input_url"),
            "timestamp":        rec.get("timestamp").strftime("%Y-%m-%d %H:%M"),
            "chatgpt_response": rec.get("result", {}).get("chatgpt_response", "")
        })
    return history

def has_keywords(result: dict) -> bool:
    """結果オブジェクトから 'キーワードが無い' を推定"""
    if not result:
        return True
    # 候補A: 集計ラベルが空
    if len(result.get("chart_labels") or []) == 0:
        # 候補B: プリミティブな件数フラグ（将来用）
        if result.get("gsc_keyword_count", 0) == 0 and len(result.get("gsc_rows") or []) == 0:
            return True
    return False


@app.route("/", methods=["GET", "POST"])
def index():
    uid = session.get("uid")
    history = get_history_for_user(uid) if uid else []
    competitors = []
    
    if request.method == "POST":
            skip_metrics = request.form.get("skip_metrics") == "on"
            uid = session.get("uid")

            # ユーザーOAuth資格情報（ない場合は None）
            creds = get_user_credentials(uid) if uid else None
            oauth_ready = creds is not None

            # 連携が無ければスキップに落とす
            effective_skip = skip_metrics or (not oauth_ready)
            if not skip_metrics and not oauth_ready:
                flash("Google Analytics / Search Console の連携がありません。データ連携なしで実行します。")

            input_url = request.form["url"].strip()
            site_root, sc_property, ga_property, sheet_id = load_site_config(uid, input_url)

            try:
                result = process_seo_improvement(
                    url=input_url,               # 画面表示用にフルURLを渡す
                    creds=creds,                 # ★ ユーザーOAuth（NoneでもOK：内部でskipする実装に）
                    sc_property=sc_property,     # ★ "sc-domain:..." or "https://..."
                    ga_property=ga_property,     # ★ "properties/123..."（未設定なら None でOK）
                    sheet_id=sheet_id,           # ★ 任意
                    skip_metrics=effective_skip, # ★ TrueならGA/GSC/Sheetsを完全スキップ
                )
            except Exception as e:
                app.logger.exception("analysis failed")
                abort(500, "内部エラーが発生しました。設定を見直してください。")
            if not effective_skip and not has_keywords(result):
                flash("⚠️ 検索キーワードが取得できませんでした。Search Console の対象プロパティ/期間/検出対象URLを確認してください。")
                return redirect(url_for ("index"))
            competitors = result.get("competitors", [])

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
                competitors=competitors,
                chatgpt_response=result.get("chatgpt_response", ""),
                history=history
            )
    return render_template(
        "index.html"
        )

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
    uid = session.get("uid")
    if not uid:
        return redirect(url_for("login"))
    exchange_code_and_store(uid)  # ← Firestoreに保存＋セッションにも入れる
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("register"))


@app.route("/result", methods=["GET","POST"])
def result():
    if request.method == 'POST':
    # 認証チェック
        if not session.get("user_authenticated") or not session.get("uid"):
            return redirect(url_for("login"))

        uid = session["uid"]

        # POST/GET 共通で使う変数を先に初期化
        new_item = None
        history      = []
        chart_labels = []
        chart_data   = {}
        competitors     = []
        input_url = request.form["url"]
        site_url  = to_sc_property(input_url)
        data      = process_seo_improvement(site_url)
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
        for idx, comp in enumerate(raw_competitors, start=1):
            competitors.append({
                "position": idx,                   # 順位を自分でセット
                "title":    comp.get("タイトル", ""),
                "url":      comp.get("URL", "")
            })

        # --- 履歴取得（常に実行） ---
        docs = (
            db.collection("improvements")
            .where("uid", "==", uid)
            .order_by("timestamp", direction=fa_firestore.Query.DESCENDING)
            .stream()
        )
        for d in docs:
            rec = d.to_dict()
            history.append({
                "id":               d.id,
                "input_url":        rec.get("input_url"),
                "timestamp":        rec.get("timestamp").strftime("%Y-%m-%d %H:%M"),
                "chatgpt_response": rec.get("result", {}).get("chatgpt_response", "")
            })

        return render_template(
            "result.html",
            site_url=input_url,
            table_html=data.get("table_html", ""),
            chart_labels=data.get("chart_labels", []),
            chart_data=data.get("chart_data", {}),
            competitors=competitors,                        
            chatgpt_response=data.get("chatgpt_response",""),
            history=history,
            new_item=new_item
        )
    else:
        if not session.get("user_authenticated") or not session.get("uid"):
            return redirect(url_for("login"))
        uid = session["uid"]
        history = load_history_from_db(uid)
        return render_template(
            "result.html",
            site_url="",
            table_html="",
            chart_labels=[],
            chart_data={},
            competitors=[],           
            chatgpt_response="",
            history=history,
            new_item=None
        )

@app.route("/delete_improvement", methods=["POST"])
def delete_improvement():
    if not session.get("user_authenticated"):
        return redirect(url_for("login"))
    doc_id = request.form["doc_id"]
    db.collection("improvements").document(doc_id).delete()
    return redirect(request.referrer or url_for("result"))


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/terms")
def terms():
    return render_template("terms.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
