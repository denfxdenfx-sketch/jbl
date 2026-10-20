# api_auth.py
import os
import secrets
import random
from functools import wraps

from flask import Blueprint, request, jsonify, g

from db import db_cursor
from auth import (
    save_otp, verify_otp_code,
    save_email_otp, verify_email_otp_code,
    send_email_otp,
    twilio_client, TWILIO_PHONE,
)

# Google verification — imported here so api_auth doesn't depend on auth.py
# for Google-related names
try:
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
except Exception:
    id_token = None
    google_requests = None
    GOOGLE_CLIENT_ID = None

api_auth_bp = Blueprint("api_auth", __name__, url_prefix="/api/auth")


# ═══════════════════════════════════════════════════════════════
# TOKEN HELPERS
# ═══════════════════════════════════════════════════════════════

def generate_token(user_id):
    """Create a random token, store it in user_tokens, return the string."""
    token = secrets.token_urlsafe(48)
    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO user_tokens (user_id, token, expires_at)
            VALUES (%s, %s, NOW() + INTERVAL '30 days')
        """, (user_id, token))
    return token


def verify_token(token):
    """Return user_id if the token is valid and not expired, else None."""
    if not token:
        return None
    with db_cursor() as cur:
        cur.execute("""
            SELECT user_id FROM user_tokens
            WHERE token = %s AND expires_at > NOW()
        """, (token,))
        row = cur.fetchone()
        if not row:
            return None
        cur.execute("UPDATE user_tokens SET last_used_at = NOW() WHERE token = %s", (token,))
        return row["user_id"]


def api_login_required(f):
    """Decorator: sets g.user_id from the Authorization header."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify(success=False, message="Not authenticated"), 401
        token = header[7:]
        user_id = verify_token(token)
        if not user_id:
            return jsonify(success=False, message="Invalid or expired token"), 401
        g.user_id = user_id
        return f(*args, **kwargs)
    return wrapper


# ═══════════════════════════════════════════════════════════════
# PHONE + OTP
# ═══════════════════════════════════════════════════════════════

@api_auth_bp.route("/send-otp", methods=["POST"])
def api_send_otp():
    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()
    if not phone:
        return jsonify(success=False, message="Phone required"), 400

    with db_cursor() as cur:
        cur.execute("SELECT id FROM users WHERE phone_number = %s", (phone,))
        if not cur.fetchone():
            return jsonify(success=False, message="Phone number not registered"), 404

    otp = str(random.randint(100000, 999999))
    save_otp(phone, otp)

    if twilio_client and TWILIO_PHONE:
        try:
            twilio_client.messages.create(
                body=f"Your OTP is {otp}. Valid for 5 minutes.",
                from_=TWILIO_PHONE, to=phone,
            )
            print(f"[twilio] OTP sent to {phone}")
        except Exception as e:
            print(f"[twilio] FAILED: {e}")
            return jsonify(success=False, message="Failed to send OTP"), 500
    else:
        print(f"[DEV] OTP for {phone}: {otp}")

    return jsonify(success=True)


@api_auth_bp.route("/verify-otp", methods=["POST"])
def api_verify_otp():
    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()
    otp = (data.get("otp") or "").strip()
    if not phone or not otp:
        return jsonify(success=False, message="Phone and OTP required"), 400

    if not verify_otp_code(phone, otp):
        return jsonify(success=False, message="Invalid or expired OTP"), 401

    with db_cursor() as cur:
        cur.execute(
            "SELECT id, email, first_name FROM users WHERE phone_number = %s",
            (phone,),
        )
        user = cur.fetchone()
    if not user:
        return jsonify(success=False, message="User not found"), 404

    token = generate_token(user["id"])
    return jsonify(success=True, token=token, redirect="/home", user=dict(user))


# ═══════════════════════════════════════════════════════════════
# EMAIL + OTP
# ═══════════════════════════════════════════════════════════════

@api_auth_bp.route("/send-email-otp", methods=["POST"])
def api_send_email_otp():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify(success=False, message="Email required"), 400

    with db_cursor() as cur:
        cur.execute("SELECT id FROM users WHERE LOWER(email) = %s", (email,))
        if not cur.fetchone():
            return jsonify(success=False, message="Email not registered"), 404

    otp = str(random.randint(100000, 999999))
    save_email_otp(email, otp)

    if not send_email_otp(email, otp):
        return jsonify(success=False, message="Failed to send email"), 500

    return jsonify(success=True)


@api_auth_bp.route("/verify-email-otp", methods=["POST"])
def api_verify_email_otp():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    otp = (data.get("otp") or "").strip()
    if not email or not otp:
        return jsonify(success=False, message="Email and OTP required"), 400

    if not verify_email_otp_code(email, otp):
        return jsonify(success=False, message="Invalid or expired OTP"), 401

    with db_cursor() as cur:
        cur.execute(
            "SELECT id, email, first_name FROM users WHERE LOWER(email) = %s",
            (email,),
        )
        user = cur.fetchone()
    if not user:
        return jsonify(success=False, message="User not found"), 404

    token = generate_token(user["id"])
    return jsonify(success=True, token=token, redirect="/home", user=dict(user))


# ═══════════════════════════════════════════════════════════════
# GOOGLE SIGN-IN (mobile)
# ═══════════════════════════════════════════════════════════════

@api_auth_bp.route("/google", methods=["POST"])
def api_google_login():
    data = request.get_json() or {}
    id_token_str = data.get("id_token")
    if not id_token_str:
        return jsonify(success=False, message="id_token required"), 400

    if not GOOGLE_CLIENT_ID:
        return jsonify(success=False, message="Google login not configured"), 500

    try:
        idinfo = id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except Exception as e:
        print(f"[google] verify failed: {e}")
        return jsonify(success=False, message="Invalid Google token"), 401

    email = idinfo.get("email", "").lower()
    if not email:
        return jsonify(success=False, message="No email in Google token"), 400

    with db_cursor() as cur:
        cur.execute(
            "SELECT id, email, first_name FROM users WHERE LOWER(email) = %s",
            (email,),
        )
        user = cur.fetchone()
    if not user:
        return jsonify(success=False, message="Email not registered. Please sign up first."), 404

    token = generate_token(user["id"])
    return jsonify(success=True, token=token, redirect="/home", user=dict(user))


# ═══════════════════════════════════════════════════════════════
# SESSION UTILITIES
# ═══════════════════════════════════════════════════════════════

@api_auth_bp.route("/me")
@api_login_required
def api_me():
    with db_cursor() as cur:
        cur.execute("""
            SELECT id, email, first_name, last_name, current_goal_id
            FROM users WHERE id = %s
        """, (g.user_id,))
        user = cur.fetchone()
    return jsonify(success=True, user=dict(user))


@api_auth_bp.route("/logout", methods=["POST"])
def api_logout():
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        token = header[7:]
        with db_cursor() as cur:
            cur.execute("DELETE FROM user_tokens WHERE token = %s", (token,))
    return jsonify(success=True)







