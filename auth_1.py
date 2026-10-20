import os
import random
from datetime import datetime, timedelta
from flask import Blueprint, render_template, session, request, jsonify, redirect
from werkzeug.security import check_password_hash
from db import db_cursor

auth_bp = Blueprint("auth", __name__)


# ─────────────────────────────────────────────────────────────
# Optional integrations
# ─────────────────────────────────────────────────────────────
try:
    from twilio.rest import Client as TwilioClient
    twilio_client = TwilioClient(
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN"),
    )
    TWILIO_PHONE = os.getenv("TWILIO_PHONE_NUMBER")
except Exception:
    twilio_client = None
    TWILIO_PHONE = None

try:
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
except Exception:
    GOOGLE_CLIENT_ID = None
    google_requests = None


# Email config
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)






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


@auth_bp.route("/login/otp")
def login_otp_page():
    phone = request.args.get("phone", "")
    return render_template("login_otp.html", phone=phone)


@auth_bp.route("/login/email")
def login_email_page():
    return render_template("login_email.html")


@auth_bp.route("/login/email-otp")
def login_email_otp_page():
    email = request.args.get("email", "")
    return render_template("login_email_otp.html", email=email)






# ═══════════════════════════════════════════════════════════════
# PHONE + OTP
# ═══════════════════════════════════════════════════════════════

def save_otp(phone, otp):
    with db_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS otp_codes (
                id SERIAL PRIMARY KEY,
                phone VARCHAR(20) NOT NULL,
                otp VARCHAR(6) NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute("""
    INSERT INTO otp_codes (phone, otp, expires_at)
    VALUES (%s, %s, NOW() + INTERVAL '5 minutes')
""", (phone, otp))


def verify_otp_code(phone, otp):
    with db_cursor() as cur:
        cur.execute("""
            SELECT id FROM otp_codes
            WHERE phone = %s AND otp = %s AND used = FALSE
              AND expires_at > NOW()
            ORDER BY created_at DESC
            LIMIT 1
        """, (phone, otp))
        row = cur.fetchone()
        if not row:
            return False
        cur.execute("UPDATE otp_codes SET used = TRUE WHERE id = %s", (row["id"],))
        return True


@auth_bp.route("/auth/send-otp", methods=["POST"])
def send_otp():
    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()

    if not phone:
        return jsonify(success=False, message="Phone required"), 400

    with db_cursor() as cur:
        cur.execute("SELECT id FROM users WHERE phone_number = %s", (phone,))
        user = cur.fetchone()

    if not user:
        return jsonify(success=False, message="Phone number not registered"), 404

    otp = str(random.randint(100000, 999999))
    save_otp(phone, otp)

    if twilio_client and TWILIO_PHONE:
        try:
            twilio_client.messages.create(
                body=f"Your OTP is {otp}. Valid for 5 minutes.",
                from_=TWILIO_PHONE,
                to=phone,
            )
            print(f"[twilio] OTP sent to {phone}")
        except Exception as e:
            print(f"[twilio] FAILED: {e}")
            return jsonify(success=False, message="Failed to send OTP"), 500
    else:
        print(f"[DEV] OTP for {phone}: {otp}")

    return jsonify(success=True)


@auth_bp.route("/auth/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()
    otp = (data.get("otp") or "").strip()

    if not phone or not otp:
        return jsonify(success=False, message="Phone and OTP required"), 400

    if not verify_otp_code(phone, otp):
        return jsonify(success=False, message="Invalid or expired OTP"), 401

    with db_cursor() as cur:
        cur.execute("SELECT id FROM users WHERE phone_number = %s", (phone,))
        user = cur.fetchone()

    if not user:
        return jsonify(success=False, message="User not found"), 404

    session["user_id"] = user["id"]
    return jsonify(success=True, redirect="/home")


# ═══════════════════════════════════════════════════════════════
# EMAIL + PASSWORD
# ═══════════════════════════════════════════════════════════════






@auth_bp.route("/auth/login-email", methods=["POST"])
def login_email():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify(success=False, message="Email and password required"), 400

    with db_cursor() as cur:
        cur.execute(
            "SELECT id, password_hash FROM users WHERE LOWER(email) = %s",
            (email,),
        )
        user = cur.fetchone()

    if not user or not user["password_hash"]:
        return jsonify(success=False, message="Invalid credentials"), 401

    if not check_password_hash(user["password_hash"], password):
        return jsonify(success=False, message="Invalid credentials"), 401

    session["user_id"] = user["id"]
    return jsonify(success=True, redirect="/home")


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
# EMAIL + OTP (NEW)
# ═══════════════════════════════════════════════════════════════

def save_email_otp(email, otp):
    """Store an email OTP with 5-minute expiry."""
    with db_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS email_otp_codes (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                otp VARCHAR(6) NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_email_otp_lookup
            ON email_otp_codes(email, otp) WHERE used = FALSE;
        """)
        cur.execute("""
            INSERT INTO email_otp_codes (email, otp, expires_at)
            VALUES (%s, %s, NOW() + INTERVAL '5 minutes')
        """, (email, otp))


def verify_email_otp_code(email, otp):
    """Check email OTP is valid and not expired. Mark as used if valid."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT id FROM email_otp_codes
            WHERE email = %s AND otp = %s AND used = FALSE
              AND expires_at > NOW()
            ORDER BY created_at DESC
            LIMIT 1
        """, (email, otp))
        row = cur.fetchone()
        if not row:
            return False
        cur.execute("UPDATE email_otp_codes SET used = TRUE WHERE id = %s", (row["id"],))
        return True


import os
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import Blueprint, render_template, session, request, jsonify, redirect
from werkzeug.security import check_password_hash
from db import db_cursor

auth_bp = Blueprint("auth", __name__)


# ─────────────────────────────────────────────────────────────
# Optional integrations
# ─────────────────────────────────────────────────────────────
try:
    from twilio.rest import Client as TwilioClient
    twilio_client = TwilioClient(
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN"),
    )
    TWILIO_PHONE = os.getenv("TWILIO_PHONE_NUMBER")
except Exception:
    twilio_client = None
    TWILIO_PHONE = None

try:
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
except Exception:
    GOOGLE_CLIENT_ID = None
    google_requests = None

# Email config
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)


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


@auth_bp.route("/login/otp")
def login_otp_page():
    phone = request.args.get("phone", "")
    return render_template("login_otp.html", phone=phone)


@auth_bp.route("/login/email")
def login_email_page():
    return render_template("login_email.html")


@auth_bp.route("/login/email-otp")
def login_email_otp_page():
    email = request.args.get("email", "")
    return render_template("login_email_otp.html", email=email)


# ═══════════════════════════════════════════════════════════════
# PHONE + OTP (unchanged)
# ═══════════════════════════════════════════════════════════════

def save_otp(phone, otp):
    with db_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS otp_codes (
                id SERIAL PRIMARY KEY,
                phone VARCHAR(20) NOT NULL,
                otp VARCHAR(6) NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute("""
            INSERT INTO otp_codes (phone, otp, expires_at)
            VALUES (%s, %s, NOW() + INTERVAL '5 minutes')
        """, (phone, otp))


def verify_otp_code(phone, otp):
    with db_cursor() as cur:
        cur.execute("""
            SELECT id FROM otp_codes
            WHERE phone = %s AND otp = %s AND used = FALSE
              AND expires_at > NOW()
            ORDER BY created_at DESC
            LIMIT 1
        """, (phone, otp))
        row = cur.fetchone()
        if not row:
            return False
        cur.execute("UPDATE otp_codes SET used = TRUE WHERE id = %s", (row["id"],))
        return True


@auth_bp.route("/auth/send-otp", methods=["POST"])
def send_otp():
    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()

    if not phone:
        return jsonify(success=False, message="Phone required"), 400

    with db_cursor() as cur:
        cur.execute("SELECT id FROM users WHERE phone_number = %s", (phone,))
        user = cur.fetchone()

    if not user:
        return jsonify(success=False, message="Phone number not registered"), 404

    otp = str(random.randint(100000, 999999))
    save_otp(phone, otp)

    if twilio_client and TWILIO_PHONE:
        try:
            twilio_client.messages.create(
                body=f"Your OTP is {otp}. Valid for 5 minutes.",
                from_=TWILIO_PHONE,
                to=phone,
            )
            print(f"[twilio] OTP sent to {phone}")
        except Exception as e:
            print(f"[twilio] FAILED: {e}")
            return jsonify(success=False, message="Failed to send OTP"), 500
    else:
        print(f"[DEV] OTP for {phone}: {otp}")

    return jsonify(success=True)


@auth_bp.route("/auth/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()
    otp = (data.get("otp") or "").strip()

    if not phone or not otp:
        return jsonify(success=False, message="Phone and OTP required"), 400

    if not verify_otp_code(phone, otp):
        return jsonify(success=False, message="Invalid or expired OTP"), 401

    with db_cursor() as cur:
        cur.execute("SELECT id FROM users WHERE phone_number = %s", (phone,))
        user = cur.fetchone()

    if not user:
        return jsonify(success=False, message="User not found"), 404

    session["user_id"] = user["id"]
    return jsonify(success=True, redirect="/home")


# ═══════════════════════════════════════════════════════════════
# EMAIL + OTP (NEW)
# ═══════════════════════════════════════════════════════════════

def save_email_otp(email, otp):
    """Store an email OTP with 5-minute expiry."""
    with db_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS email_otp_codes (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                otp VARCHAR(6) NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_email_otp_lookup
            ON email_otp_codes(email, otp) WHERE used = FALSE;
        """)
        cur.execute("""
            INSERT INTO email_otp_codes (email, otp, expires_at)
            VALUES (%s, %s, NOW() + INTERVAL '5 minutes')
        """, (email, otp))


def verify_email_otp_code(email, otp):
    """Check email OTP is valid and not expired. Mark as used if valid."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT id FROM email_otp_codes
            WHERE email = %s AND otp = %s AND used = FALSE
              AND expires_at > NOW()
            ORDER BY created_at DESC
            LIMIT 1
        """, (email, otp))
        row = cur.fetchone()
        if not row:
            return False
        cur.execute("UPDATE email_otp_codes SET used = TRUE WHERE id = %s", (row["id"],))
        return True


def send_email_otp(to_email, otp):
    """Send OTP via SMTP. Falls back to console print in dev mode."""
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS]):
        print(f"[DEV EMAIL] OTP for {to_email}: {otp}")
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Your login code"
        msg["From"] = SMTP_FROM
        msg["To"] = to_email

        text = f"Your login code is {otp}. Valid for 5 minutes."
        html = f"""
        <html><body>
          <p>Your login code is:</p>
          <h2 style="font-family:monospace;letter-spacing:4px;">{otp}</h2>
          <p>Valid for 5 minutes. Do not share this code.</p>
        </body></html>
        """
        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        print(f"[email] OTP sent to {to_email}")
        return True
    except Exception as e:
        print(f"[email] FAILED: {e}")
        return False


@auth_bp.route("/auth/send-email-otp", methods=["POST"])
def send_email_otp_route():
    """Receive email, check it exists, generate OTP, send it."""
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify(success=False, message="Email required"), 400

    # Check if email exists in users
    with db_cursor() as cur:
        cur.execute("SELECT id FROM users WHERE LOWER(email) = %s", (email,))
        user = cur.fetchone()

    if not user:
        return jsonify(success=False, message="Email not registered"), 404

    # Generate and store OTP
    otp = str(random.randint(100000, 999999))
    save_email_otp(email, otp)

    # Send it
    if not send_email_otp(email, otp):
        return jsonify(success=False, message="Failed to send email"), 500

    return jsonify(success=True)


@auth_bp.route("/auth/verify-email-otp", methods=["POST"])
def verify_email_otp_route():
    """Receive email + OTP, verify it, log the user in."""
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    otp = (data.get("otp") or "").strip()

    if not email or not otp:
        return jsonify(success=False, message="Email and OTP required"), 400

    if not verify_email_otp_code(email, otp):
        return jsonify(success=False, message="Invalid or expired OTP"), 401

    # Find the user
    with db_cursor() as cur:
        cur.execute("SELECT id FROM users WHERE LOWER(email) = %s", (email,))
        user = cur.fetchone()

    if not user:
        return jsonify(success=False, message="User not found"), 404

    session["user_id"] = user["id"]
    return jsonify(success=True, redirect="/home")





# ═══════════════════════════════════════════════════════════════
# SIGNUP (email + OTP)
# ═══════════════════════════════════════════════════════════════

def save_signup_otp(email, otp):
    """Store a signup OTP with 5-minute expiry."""
    with db_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS signup_otp_codes (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                otp VARCHAR(6) NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_signup_otp_lookup
            ON signup_otp_codes(email, otp) WHERE used = FALSE;
        """)
        cur.execute("""
            INSERT INTO signup_otp_codes (email, otp, expires_at)
            VALUES (%s, %s, NOW() + INTERVAL '5 minutes')
        """, (email, otp))


def verify_signup_otp_code(email, otp):
    """Check signup OTP is valid and not expired. Mark as used if valid."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT id FROM signup_otp_codes
            WHERE email = %s AND otp = %s AND used = FALSE
              AND expires_at > NOW()
            ORDER BY created_at DESC
            LIMIT 1
        """, (email, otp))
        row = cur.fetchone()
        if not row:
            return False
        cur.execute("UPDATE signup_otp_codes SET used = TRUE WHERE id = %s", (row["id"],))
        return True


@auth_bp.route("/signup")
def signup_page():
    return render_template("signup.html")


@auth_bp.route("/signup/otp")
def signup_otp_page():
    email = request.args.get("email", "")
    return render_template("signup_otp.html", email=email)


@auth_bp.route("/auth/signup-send-otp", methods=["POST"])
def signup_send_otp():
    """Receive email, check it's NOT already registered, send OTP."""
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify(success=False, message="Email required"), 400

    # Check if email ALREADY exists — if yes, reject
    with db_cursor() as cur:
        cur.execute("SELECT id FROM users WHERE LOWER(email) = %s", (email,))
        existing = cur.fetchone()

    if existing:
        return jsonify(success=False, message="Email already registered. Please log in."), 409

    # Generate and store OTP
    otp = str(random.randint(100000, 999999))
    save_signup_otp(email, otp)

    # Send it
    if not send_email_otp(email, otp):
        return jsonify(success=False, message="Failed to send email"), 500

    return jsonify(success=True)


@auth_bp.route("/auth/signup-verify-otp", methods=["POST"])
def signup_verify_otp():
    """Verify OTP, create the user, log them in."""
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    otp = (data.get("otp") or "").strip()

    if not email or not otp:
        return jsonify(success=False, message="Email and OTP required"), 400

    if not verify_signup_otp_code(email, otp):
        return jsonify(success=False, message="Invalid or expired OTP"), 401

    with db_cursor() as cur:
        # Race condition guard
        cur.execute("SELECT id FROM users WHERE LOWER(email) = %s", (email,))
        existing = cur.fetchone()

        if existing:
            session["user_id"] = existing["id"]
            return jsonify(success=True, redirect="/goals")

        cur.execute("""
            INSERT INTO users (email) VALUES (%s) RETURNING id
        """, (email,))

        new_user = cur.fetchone()
        user_id = new_user["id"]

    session["user_id"] = user_id
    return jsonify(success=True, redirect="/goals")



# ═══════════════════════════════════════════════════════════════
# SIGNUP — PHONE NUMBER + OTP
# ═══════════════════════════════════════════════════════════════

def save_signup_number_otp(phone, otp):
    """Store a phone signup OTP with 5-minute expiry."""
    with db_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS signup_number_otp_codes (
                id SERIAL PRIMARY KEY,
                phone VARCHAR(20) NOT NULL,
                otp VARCHAR(6) NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_signup_number_otp_lookup
            ON signup_number_otp_codes(phone, otp) WHERE used = FALSE;
        """)
        cur.execute("""
            INSERT INTO signup_number_otp_codes (phone, otp, expires_at)
            VALUES (%s, %s, NOW() + INTERVAL '5 minutes')
        """, (phone, otp))


def verify_signup_number_otp_code(phone, otp):
    """Check signup phone OTP is valid and not expired."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT id FROM signup_number_otp_codes
            WHERE phone = %s AND otp = %s AND used = FALSE
              AND expires_at > NOW()
            ORDER BY created_at DESC
            LIMIT 1
        """, (phone, otp))
        row = cur.fetchone()
        if not row:
            return False
        cur.execute("UPDATE signup_number_otp_codes SET used = TRUE WHERE id = %s", (row["id"],))
        return True


@auth_bp.route("/setup-number/otp")
def setup_number_otp_page():
    phone = request.args.get("phone", "")
    return render_template("setup_number_otp.html", phone=phone)


@auth_bp.route("/auth/signup-number-send-otp", methods=["POST"])
def signup_number_send_otp():
    """Receive phone, check it's not taken, send OTP via Twilio."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, message="Not logged in"), 401

    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()

    if not phone:
        return jsonify(success=False, message="Phone required"), 400

    # Check if this phone is already registered to a different user
    with db_cursor() as cur:
        cur.execute("SELECT id FROM users WHERE phone_number = %s", (phone,))
        existing = cur.fetchone()

    if existing and existing["id"] != user_id:
        return jsonify(success=False, message="Phone number already in use"), 409

    # Generate and store OTP
    otp = str(random.randint(100000, 999999))
    save_signup_number_otp(phone, otp)

    # Send via Twilio (or console print in dev)
    if twilio_client and TWILIO_PHONE:
        try:
            twilio_client.messages.create(
                body=f"Your verification code is {otp}. Valid for 5 minutes.",
                from_=TWILIO_PHONE,
                to=phone,
            )
            print(f"[twilio] Signup OTP sent to {phone}")
        except Exception as e:
            print(f"[twilio] FAILED: {e}")
            return jsonify(success=False, message="Failed to send OTP"), 500
    else:
        print(f"[DEV] Signup OTP for {phone}: {otp}")

    return jsonify(success=True)


@auth_bp.route("/auth/signup-number-verify-otp", methods=["POST"])
def signup_number_verify_otp():
    """Verify the phone OTP, save it to the user, redirect to home."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, message="Not logged in"), 401

    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()
    otp = (data.get("otp") or "").strip()

    if not phone or not otp:
        return jsonify(success=False, message="Phone and OTP required"), 400

    if not verify_signup_number_otp_code(phone, otp):
        return jsonify(success=False, message="Invalid or expired OTP"), 401

    # Save the phone number to the user
    with db_cursor() as cur:
        cur.execute("UPDATE users SET phone_number = %s WHERE id = %s",
                    (phone, user_id))

    return jsonify(success=True, redirect="/home")

