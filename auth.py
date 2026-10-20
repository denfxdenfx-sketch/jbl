import os
from flask import Blueprint, render_template, session, request, jsonify, redirect
from werkzeug.security import check_password_hash, generate_password_hash
from db import db_cursor

auth_bp = Blueprint("auth", __name__)


# ─────────────────────────────────────────────────────────────
# Optional integrations (Google OAuth)
# ─────────────────────────────────────────────────────────────
try:
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
except Exception:
    GOOGLE_CLIENT_ID = None
    google_requests = None


# ═══════════════════════════════════════════════════════════════
# PAGE ROUTES
# ═══════════════════════════════════════════════════════════════

@auth_bp.route("/check")
def check():
    if not session.get("user_id"):
        return render_template("login.html")
    return redirect("/home")


@auth_bp.route("/login")
def login_page():
    return render_template("login.html")


@auth_bp.route("/signup")
def signup_page():
    return render_template("signup.html")


# ═══════════════════════════════════════════════════════════════
# NEW LOGIN (Email OR Phone + Password)
# ═══════════════════════════════════════════════════════════════

@auth_bp.route("/auth/login", methods=["POST"])
def handle_login():
    data = request.get_json() or {}
    identifier = (data.get("identifier") or "").strip()  # Can be Email or Phone
    password = data.get("password") or ""

    if not identifier or not password:
        return jsonify(success=False, message="Credentials required"), 400

    # Check if the identifier is an email (contains @) or phone
    is_email = "@" in identifier
    identifier = identifier.lower() if is_email else identifier

    with db_cursor() as cur:
        if is_email:
            cur.execute("SELECT id, password_hash FROM users WHERE LOWER(email) = %s", (identifier,))
        else:
            cur.execute("SELECT id, password_hash FROM users WHERE phone_number = %s", (identifier,))
            
        user = cur.fetchone()

    if not user or not user["password_hash"]:
        return jsonify(success=False, message="Invalid credentials"), 401

    if not check_password_hash(user["password_hash"], password):
        return jsonify(success=False, message="Invalid credentials"), 401

    # Log them in and send to Home
    session["user_id"] = user["id"]
    return jsonify(success=True, redirect="/home")


# ═══════════════════════════════════════════════════════════════
# NEW SIGNUP (Email + Phone + Password)
# ═══════════════════════════════════════════════════════════════

@auth_bp.route("/auth/signup", methods=["POST"])
def handle_signup():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    password = data.get("password") or ""

    # 1. Basic Validation
    if not email or not phone or not password:
        return jsonify(success=False, message="All fields are required"), 400

    if len(password) < 6:
        return jsonify(success=False, message="Password must be at least 6 characters"), 400

    # 2. Check if Email or Phone already exists
    with db_cursor() as cur:
        cur.execute("SELECT id FROM users WHERE LOWER(email) = %s OR phone_number = %s", (email, phone))
        existing = cur.fetchone()

    if existing:
        return jsonify(success=False, message="Email or Phone number already registered"), 409

    # 3. Create the user
    password_hash = generate_password_hash(password)
    
    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO users (email, phone_number, password_hash) 
            VALUES (%s, %s, %s) RETURNING id
        """, (email, phone, password_hash))
        
        new_user = cur.fetchone()
        user_id = new_user["id"]

    # 4. Log them in and send to Goals
    session["user_id"] = user_id
    return jsonify(success=True, redirect="/goals")


# ═══════════════════════════════════════════════════════════════
# GOOGLE OAUTH
# ═══════════════════════════════════════════════════════════════

@auth_bp.route("/auth/google")
def google_start():
    if not GOOGLE_CLIENT_ID:
        return jsonify(success=False, message="Google login not configured"), 500

    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    from urllib.parse import urlencode
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return redirect(url)


@auth_bp.route("/auth/google/callback")
def google_callback():
    code = request.args.get("code")
    if not code:
        return redirect("/login")

    import requests as http

    token_res = http.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI"),
        "grant_type": "authorization_code",
    })

    if token_res.status_code != 200:
        return redirect("/login?error=google_token_failed")

    tokens = token_res.json()
    id_token_str = tokens.get("id_token")

    try:
        idinfo = id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            os.getenv("GOOGLE_CLIENT_ID"),
        )
    except Exception:
        return redirect("/login?error=google_verify_failed")

    email = idinfo.get("email", "").lower()
    if not email:
        return redirect("/login?error=google_no_email")

    with db_cursor() as cur:
        cur.execute("SELECT id FROM users WHERE LOWER(email) = %s", (email,))
        user = cur.fetchone()

    if not user:
        return redirect("/login?error=email_not_registered")

    session["user_id"] = user["id"]
    return redirect("/home")

# ═══════════════════════════════════════════════════════════════
# LOGOUT
# ═══════════════════════════════════════════════════════════════

@auth_bp.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect("/login")