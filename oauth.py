# oauth.py
import os
import json
import pathlib
import requests
from flask import session, redirect, request, url_for
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # 開発用。httpsでないときでも許可。

CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",  # GSC読み取り
    "https://www.googleapis.com/auth/analytics.readonly"    # GA読み取り
]

def create_flow():
    return Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for("oauth2callback", _external=True)
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
