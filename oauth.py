import base64
from pathlib import Path
import os
from datetime import datetime

from flask import session, url_for, request
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# Firestore に永続化（※ firebase_admin.initialize_app は app.py 側で済ませておく）
from firebase_admin import firestore

# --- 1) スコープ拡張（GA/GSCに加えて Sheets/Drive も扱えるように） ---
SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",   # GSC
    "https://www.googleapis.com/auth/analytics.readonly",    # GA4 Data API
    "https://www.googleapis.com/auth/spreadsheets",          # Sheets 書き込み
    "https://www.googleapis.com/auth/drive",            # ユーザーDriveに新規作成
]

# --- 2) client_secret.json の配置（Cloud Run 環境変数からのBase64対応） ---
b64 = os.getenv("GOOGLE_OAUTH2_CLIENT_SECRET_JSON_BASE64")
if b64:
    credentials_path = Path(__file__).parent / "client_secret.json"
    credentials_path.write_bytes(base64.b64decode(b64))
    CLIENT_SECRETS_FILE = str(credentials_path)
else:
    CLIENT_SECRETS_FILE = "client_secret.json"


# ========== 既存：Flow作成 ==========
def create_flow():
    return Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for("oauth2callback", _external=True, _scheme="https"),
    )


# ========== 追加：認可URLを作る（refresh_tokenを確実に得る指定を付ける） ==========
def build_authorization_url():
    flow = create_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",          # ★ refresh_token を得る
        include_granted_scopes=True,
        prompt="consent",               # ★ すでに承認済でも毎回 consent を出して refresh_token を返させる
    )
    session["state"] = state
    return auth_url


# ========== 既存：セッションから資格情報を読む（後方互換。今後は Firestore を使う） ==========
def get_credentials_from_session():
    if "credentials" not in session:
        return None
    return Credentials(**session["credentials"])


# ========== 既存：セッションへ保存（後方互換。今後は Firestore を使う） ==========
def store_credentials_in_session(creds):
    session["credentials"] = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or []),
    }


# ========== 追加：Firestore にユーザー単位で保存 ==========
def _save_user_credentials(uid: str, creds: Credentials):
    firestore.client().collection("user_google_tokens").document(uid).set({
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or []),
        "expiry": creds.expiry.isoformat() if getattr(creds, "expiry", None) else None,
        "updatedAt": datetime.utcnow().isoformat(),
    }, merge=True)


# ========== 追加：Firestore から取得＋期限切れなら自動リフレッシュ ==========
def get_user_credentials(uid: str) -> Credentials | None:
    doc = firestore.client().collection("user_google_tokens").document(uid).get()
    if not doc.exists:
        return None
    d = doc.to_dict() or {}
    creds = Credentials(
        token=d.get("token"),
        refresh_token=d.get("refresh_token"),
        token_uri=d.get("token_uri"),
        client_id=d.get("client_id"),
        client_secret=d.get("client_secret"),
        scopes=d.get("scopes"),
    )
    # 自動リフレッシュ
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_user_credentials(uid, creds)
    return creds


# ========== 追加：コールバックでコードをトークンに交換 → Firestoreへ保存 ==========
def exchange_code_and_store(uid: str):
    state = session.get("state")
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=url_for("oauth2callback", _external=True, _scheme="https"),
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    _save_user_credentials(uid, creds)      # ★ 永続化
    store_credentials_in_session(creds)     # （任意）後方互換でセッションにも入れておく
    return creds
