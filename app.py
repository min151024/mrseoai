from urllib.parse import urlparse
from flask import Flask, redirect, session, url_for, request, render_template
from oauth import create_flow, get_credentials_from_session, store_credentials_in_session
from main import process_seo_improvement
import os

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "defaultsecretkey")  # セッション用

def to_domain_property(url):
    parsed = urlparse(url)
    domain = parsed.hostname.replace("www.", "")
    return f"sc-domain:{domain}"

def is_authenticated():
    return session.get("user_authenticated", False)

@app.route("/", methods=["GET", "POST"])
def index():
    if not is_authenticated() or "credentials" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        input_url = request.form["url"]
        site_url = to_domain_property(input_url)
        result = process_seo_improvement(site_url)

        return render_template(
            "result.html",
            site_url=input_url,
            table_html=result["table_html"],
            chart_labels=result["chart_labels"],
            chart_data=result["chart_data"],
            competitors=result["competitors"],
            chatgpt_response=result.get("chatgpt_response", "")
        )

    return render_template("index.html")



@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        session["user_authenticated"] = True
        flow = create_flow()
        auth_url, _ = flow.authorization_url(
            prompt="consent",
            access_type="offline",
            include_granted_scopes="true"
        )
        return redirect(auth_url)


    return render_template("register.html",
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



@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        session["user_authenticated"] = True
        return redirect(url_for("index"))

    return render_template("login.html",
        FIREBASE_API_KEY=os.getenv("FIREBASE_API_KEY"),
        FIREBASE_AUTH_DOMAIN=os.getenv("FIREBASE_AUTH_DOMAIN"),
        FIREBASE_PROJECT_ID=os.getenv("FIREBASE_PROJECT_ID"),
        FIREBASE_APP_ID=os.getenv("FIREBASE_APP_ID")
    )


@app.route("/result")
def show_result():
    return render_template("result.html", site_url="", table_html="", chart_labels=[], chart_data=[], competitors=[])


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
