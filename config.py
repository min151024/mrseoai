# config.py
GOOGLE_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",  # Driveにシート新規作成するなら
]

# 収容コレクション名
FIRESTORE_COLLECTION_USER_TOKENS = "user_google_tokens"
FIRESTORE_COLLECTION_SITES      = "sites"  # サブコレクションに {uid}/owned/{siteKey}
