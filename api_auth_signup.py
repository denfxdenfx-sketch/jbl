# api_auth_signup.py
#
# JSON signup + onboarding routes.
# URL prefix: /api/auth
#
# Covers:
#   - Email signup OTP (send + verify)
#   - Phone number signup OTP (send + verify)
#
# NOTE: Goal selection and name-setting live in api_home.py
#       (/api/goals, /api/goals/select, /api/user/name).

import random
from flask import Blueprint, request, jsonify, g
from db import db_cursor
from api_auth import api_login_required, generate_token


api_auth_signup_bp = Blueprint(
    "api_auth_signup",
    __name__,
    url_prefix="/api/auth",
)


# ═══════════════════════════════════════════════════════════════
# EMAIL SIGNUP — helper functions
# ═══════════════════════════════════════════════════════════════

def _save_signup_otp(email, otp):
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


def _verify_signup_otp_code(email, otp):
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
        cur.execute(
            "UPDATE signup_otp_codes SET used = TRUE WHERE id = %s",
            (row["id"],),
        )
        return True


# ═══════════════════════════════════════════════════════════════
# EMAIL SIGNUP — routes
# ═══════════════════════════════════════════════════════════════

@api_auth_signup_bp.route("/signup-send-otp", methods=["POST"])
def api_signup_send_otp():
    """
    Receive email, check it's NOT already registered, send OTP.
    Public route — no auth required.
    """
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify(success=False, message="Email required"), 400

    # Check if email ALREADY exists — if yes, reject
    with db_cursor() as cur:
        cur.execute(
            "SELECT id FROM users WHERE LOWER(email) = %s",
            (email,),
        )
        existing = cur.fetchone()

    if existing:
        return jsonify(
            success=False,
            message="Email already registered. Please log in.",
        ), 409

    # Generate and store OTP
    otp = str(random.randint(100000, 999999))
    _save_signup_otp(email, otp)

    # Send it
    try:
        from auth import send_email_otp
        sent = send_email_otp(email, otp)
    except Exception as e:
        print(f"[signup] send_email_otp failed: {e}")
        sent = False

    if not sent:
        return jsonify(success=False, message="Failed to send email"), 500

    return jsonify(success=True)


@api_auth_signup_bp.route("/signup-verify-otp", methods=["POST"])
def api_signup_verify_otp():
    """
    Verify OTP, create the user, return a token.
    Public route — no auth required.
    """
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    otp = (data.get("otp") or "").strip()

    if not email or not otp:
        return jsonify(success=False, message="Email and OTP required"), 400

    if not _verify_signup_otp_code(email, otp):
        return jsonify(success=False, message="Invalid or expired OTP"), 401

    with db_cursor() as cur:
        # Race condition guard — user may already exist
        cur.execute(
            "SELECT id FROM users WHERE LOWER(email) = %s",
            (email,),
        )
        existing = cur.fetchone()

        if existing:
            user_id = existing["id"]
        else:
            cur.execute(
                "INSERT INTO users (email) VALUES (%s) RETURNING id",
                (email,),
            )
            user_id = cur.fetchone()["id"]

    # Issue a token for subsequent API calls
    token = generate_token(user_id)

    return jsonify(
        success=True,
        token=token,
        user_id=user_id,
    )


# ═══════════════════════════════════════════════════════════════
# PHONE SIGNUP — helper functions
# ═══════════════════════════════════════════════════════════════

def _save_signup_number_otp(phone, otp):
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


def _verify_signup_number_otp_code(phone, otp):
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
        cur.execute(
            "UPDATE signup_number_otp_codes SET used = TRUE WHERE id = %s",
            (row["id"],),
        )
        return True


# ═══════════════════════════════════════════════════════════════
# PHONE SIGNUP — routes
# ═══════════════════════════════════════════════════════════════

@api_auth_signup_bp.route("/signup-number-send-otp", methods=["POST"])
@api_login_required
def api_signup_number_send_otp():
    """
    Receive phone, check it's not taken, send OTP via Twilio.
    Requires login (user must have completed email OTP step).
    """
    user_id = g.user_id
    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()

    if not phone:
        return jsonify(success=False, message="Phone required"), 400

    # Check if this phone is already registered to a DIFFERENT user
    with db_cursor() as cur:
        cur.execute(
            "SELECT id FROM users WHERE phone_number = %s",
            (phone,),
        )
        existing = cur.fetchone()

    if existing and existing["id"] != user_id:
        return jsonify(
            success=False,
            message="Phone number already in use",
        ), 409

    # Generate and store OTP
    otp = str(random.randint(100000, 999999))
    _save_signup_number_otp(phone, otp)

    # Send via Twilio (or console print in dev)
    try:
        from auth import twilio_client, TWILIO_PHONE
    except Exception:
        twilio_client = None
        TWILIO_PHONE = None

    if twilio_client and TWILIO_PHONE:
        try:
            twilio_client.messages.create(
                body=(
                    f"Your verification code is {otp}. "
                    "Valid for 5 minutes."
                ),
                from_=TWILIO_PHONE,
                to=phone,
            )
            print(f"[twilio] Signup OTP sent to {phone}")
        except Exception as e:
            print(f"[twilio] FAILED: {e}")
            return jsonify(success=False, message="Failed to send OTP"), 500
    else:
        # Dev fallback — log the OTP so you can test
        print(f"[DEV] Signup OTP for {phone}: {otp}")

    return jsonify(success=True)


@api_auth_signup_bp.route("/signup-number-verify-otp", methods=["POST"])
@api_login_required
def api_signup_number_verify_otp():
    """
    Verify the phone OTP, save it to the user.
    Requires login (same session as send).
    """
    user_id = g.user_id
    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()
    otp = (data.get("otp") or "").strip()

    if not phone or not otp:
        return jsonify(
            success=False,
            message="Phone and OTP required",
        ), 400

    if not _verify_signup_number_otp_code(phone, otp):
        return jsonify(
            success=False,
            message="Invalid or expired OTP",
        ), 401

    # Save the phone number to the user
    with db_cursor() as cur:
        cur.execute(
            "UPDATE users SET phone_number = %s WHERE id = %s",
            (phone, user_id),
        )

    return jsonify(success=True)