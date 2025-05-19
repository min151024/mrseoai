import os
import base64


if "GOOGLE_CREDS_BASE64" in os.environ:
    with open("credentials.json", "wb") as f:
        f.write(base64.b64decode(os.environ["GOOGLE_CREDS_BASE64"]))