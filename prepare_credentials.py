import os
import base64

print("🔥 prepare_credentials.py 実行された！")
print("カレントディレクトリ:", os.getcwd())

# credentials.json を作成
if "GOOGLE_CREDS_BASE64" in os.environ:
    with open("credentials.json", "wb") as f:
        f.write(base64.b64decode(os.environ["GOOGLE_CREDS_BASE64"]))

# ga_credentials.json を作成
if "GA_CREDS_BASE64" in os.environ:
    with open("ga_credentials.json", "wb") as f:
        f.write(base64.b64decode(os.environ["GA_CREDS_BASE64"]))
