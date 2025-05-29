import base64
from pathlib import Path
import os
from flask import session, redirect, request, url_for
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

SCOPES = [
        "https://www.googleapis.com/auth/webmasters.readonly",  # GSC読み取り
        "https://www.googleapis.com/auth/analytics.readonly"    # GA読み取り
    ]

b64 = os.getenv("GOOGLE_OAUTH2_CLIENT_SECRET_JSON_BASE64")
if b64:
    credentials_path = Path(__file__).parent / "client_secret.json"
    credentials_path.write_bytes(base64.b64decode(b64))
    CLIENT_SECRETS_FILE = str(credentials_path)
else:
    CLIENT_SECRETS_FILE = "client_secret.json"

def create_flow():
    return Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for("oauth2callback", _external=True, _scheme="https")
    )

def get_credentials_from_session():
    if "credentials" not in session:
        return None
    return Credentials(**session["credentials"])

def store_credentials_in_session(creds):
    session["credentials"] = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes
    }
