# api_auth.py
import os
import secrets
from functools import wraps

from flask import Blueprint, request, jsonify, g
from werkzeug.security import check_password_hash, generate_password_hash

from db import db_cursor

# Google verification
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
# LOGIN API (Email OR Phone + Password)
# ═══════════════════════════════════════════════════════════════

@api_auth_bp.route("/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    identifier = (data.get("identifier") or "").strip()
    password = data.get("password") or ""

    if not identifier or not password:
        return jsonify(success=False, message="Credentials required"), 400

    is_email = "@" in identifier
    identifier = identifier.lower() if is_email else identifier

    with db_cursor() as cur:
        if is_email:
            cur.execute("SELECT id, email, first_name, password_hash FROM users WHERE LOWER(email) = %s", (identifier,))
        else:
            cur.execute("SELECT id, email, first_name, password_hash FROM users WHERE phone_number = %s", (identifier,))
        user = cur.fetchone()

    if not user or not user["password_hash"]:
        return jsonify(success=False, message="Invalid credentials"), 401

    if not check_password_hash(user["password_hash"], password):
        return jsonify(success=False, message="Invalid credentials"), 401

    token = generate_token(user["id"])
    return jsonify(
        success=True, 
        token=token, 
        redirect="/home", 
        user={
            "id": user["id"], 
            "email": user["email"], 
            "first_name": user["first_name"]
        }
    )


# ═══════════════════════════════════════════════════════════════
# SIGNUP API (Email + Phone + Password)
# ═══════════════════════════════════════════════════════════════

@api_auth_bp.route("/signup", methods=["POST"])
def api_signup():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    password = data.get("password") or ""

    if not email or not phone or not password:
        return jsonify(success=False, message="All fields are required"), 400

    if len(password) < 6:
        return jsonify(success=False, message="Password must be at least 6 characters"), 400

    with db_cursor() as cur:
        cur.execute("SELECT id FROM users WHERE LOWER(email) = %s OR phone_number = %s", (email, phone))
        existing = cur.fetchone()

    if existing:
        return jsonify(success=False, message="Email or Phone number already registered"), 409

    password_hash = generate_password_hash(password)

    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO users (email, phone_number, password_hash) 
            VALUES (%s, %s, %s) RETURNING id, email, first_name
        """, (email, phone, password_hash))
        user = cur.fetchone()

    token = generate_token(user["id"])
    return jsonify(
        success=True, 
        token=token, 
        redirect="/goals", 
        user={
            "id": user["id"], 
            "email": user["email"], 
            "first_name": user["first_name"]
        }
    )


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
    return jsonify(
        success=True, 
        token=token, 
        redirect="/home", 
        user={
            "id": user["id"], 
            "email": user["email"], 
            "first_name": user["first_name"]
        }
    )


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


# ═══════════════════════════════════════════════════════════════
# ONBOARDING API (Goals + Name) — Flutter mobile
# ═══════════════════════════════════════════════════════════════

# ─── List all goals ────────────────────────────────────────────
@api_auth_bp.route("/goals", methods=["GET"])
@api_login_required
def api_list_goals():
    with db_cursor() as cur:
        cur.execute("SELECT id, name FROM goals ORDER BY id")
        goals = cur.fetchall()

    return jsonify(
        success=True,
        goals=[dict(g) for g in goals],
    )


# ─── Select a goal ─────────────────────────────────────────────
@api_auth_bp.route("/goals/select", methods=["POST"])
@api_login_required
def api_select_goal():
    user_id = g.user_id
    data = request.get_json() or {}
    goal_id = data.get("goal_id")

    if not goal_id:
        return jsonify(success=False, message="goal_id required"), 400

    with db_cursor() as cur:
        cur.execute("SELECT id FROM goals WHERE id = %s", (goal_id,))
        if not cur.fetchone():
            return jsonify(success=False, message="Goal not found"), 404

        cur.execute(
            "UPDATE users SET current_goal_id = %s WHERE id = %s",
            (goal_id, user_id),
        )

    return jsonify(success=True, redirect="/name")


# ─── Set user's display name ───────────────────────────────────
@api_auth_bp.route("/user/set-name", methods=["POST"])
@api_login_required
def api_set_name():
    user_id = g.user_id
    data = request.get_json() or {}
    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()

    if not first_name:
        return jsonify(success=False, message="First name required"), 400

    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE users SET first_name = %s, last_name = %s WHERE id = %s
            """,
            (first_name, last_name or None, user_id),
        )

    return jsonify(success=True, redirect="/home")


# ═══════════════════════════════════════════════════════════════
# LANDING HOME API — dashboard data for the post-login screen
# ═══════════════════════════════════════════════════════════════

@api_auth_bp.route("/home/landing", methods=["GET"])
@api_login_required
def api_landing_home():
    user_id = g.user_id

    with db_cursor() as cur:
        # 1. User profile
        cur.execute("""
            SELECT
                u.first_name,
                u.last_name,
                u.current_goal_id,
                g.name AS goal_name
            FROM users u
            LEFT JOIN goals g ON u.current_goal_id = g.id
            WHERE u.id = %s
        """, (user_id,))
        user = cur.fetchone()

        if not user:
            return jsonify(success=False, message="User not found"), 404

        # 2. Recent questions answered by this user (latest 5)
        cur.execute("""
            SELECT
                ua.id,
                ua.is_correct,
                ua.answered_at,
                q.id            AS question_id,
                q.text          AS question_text,
                t.id            AS topic_id,
                t.name          AS topic_name,
                s.id            AS subject_id,
                s.name          AS subject_name
            FROM user_answers ua
            JOIN questions q ON ua.question_id = q.id
            JOIN topics t    ON q.topic_id = t.id
            JOIN chapters c  ON t.chapter_id = c.id
            JOIN subjects s  ON c.subject_id = s.id
            WHERE ua.user_id = %s
              AND ua.context = 'practice'
            ORDER BY ua.answered_at DESC
            LIMIT 5
        """, (user_id,))
        recent_rows = cur.fetchall()

        # 3. Is each of these bookmarked?
        recent_qids = [r["question_id"] for r in recent_rows]
        bookmarked = set()
        if recent_qids:
            cur.execute("""
                SELECT question_id FROM user_bookmarks
                WHERE user_id = %s AND question_id = ANY(%s)
            """, (user_id, recent_qids))
            bookmarked = {r["question_id"] for r in cur.fetchall()}

    recent_questions = [
        {
            "question_id": r["question_id"],
            "text": r["question_text"][:120] + ("..." if len(r["question_text"]) > 120 else ""),
            "subject": r["subject_name"],
            "subject_id": r["subject_id"],
            "topic": r["topic_name"],
            "topic_id": r["topic_id"],
            "is_correct": r["is_correct"],
            "is_bookmarked": r["question_id"] in bookmarked,
            "answered_at": r["answered_at"].isoformat() if r["answered_at"] else None,
        }
        for r in recent_rows
    ]

    return jsonify(
        success=True,
        user={
            "first_name": user["first_name"],
            "last_name": user["last_name"],
            "goal_id": user["current_goal_id"],
            "goal_name": user["goal_name"],
        },
        recent_questions=recent_questions,
    )



# ═══════════════════════════════════════════════════════════════
# PLANS API — list plans for the user's current goal
# ═══════════════════════════════════════════════════════════════

@api_auth_bp.route("/plans", methods=["GET"])
@api_login_required
def api_list_plans():
    user_id = g.user_id

    with db_cursor() as cur:
        # Get user's current goal AND the goal name
        cur.execute("""
            SELECT u.current_goal_id, g.name AS goal_name 
            FROM users u
            JOIN goals g ON u.current_goal_id = g.id
            WHERE u.id = %s
        """, (user_id,))
        user = cur.fetchone()
        
        if not user or not user["current_goal_id"]:
            return jsonify(success=False, message="No goal selected"), 400

        goal_id = user["current_goal_id"]
        goal_name = user["goal_name"]

        cur.execute("""
            SELECT id, name, duration_days, price, currency
            FROM plans WHERE goal_id = %s ORDER BY duration_days
        """, (goal_id,))
        plans = cur.fetchall()

    return jsonify(
        success=True,
        goal_id=goal_id,
        goal_name=goal_name, # 👈 ADD THIS
        plans=[
            {
                "id": p["id"],
                "name": p["name"],
                "duration_days": p["duration_days"],
                "duration_months": p["duration_days"] // 30,
                "price": float(p["price"]),
                "currency": p["currency"],
            }
            for p in plans
        ],
    )

# ═══════════════════════════════════════════════════════════════
# PAYMENT — CREATE ORDER
# ═══════════════════════════════════════════════════════════════

@api_auth_bp.route("/payment/create-order", methods=["POST"])
@api_login_required
def api_create_order():
    import os
    import razorpay
    from datetime import datetime

    user_id = g.user_id
    data = request.get_json() or {}
    plan_id = data.get("plan_id")

    if not plan_id:
        return jsonify(success=False, message="plan_id required"), 400

    # Fetch plan — never trust price from frontend
    with db_cursor() as cur:
        cur.execute("""
            SELECT id, goal_id, name, duration_days, price, currency
            FROM plans WHERE id = %s
        """, (plan_id,))
        plan = cur.fetchone()

    if not plan:
        return jsonify(success=False, message="Plan not found"), 404

    # Razorpay client
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        return jsonify(success=False, message="Payment not configured"), 500

    client = razorpay.Client(auth=(key_id, key_secret))

    # Razorpay wants paise
    amount_paise = int(round(float(plan["price"]) * 100))

    try:
        order = client.order.create({
            "amount": amount_paise,
            "currency": plan["currency"] or "INR",
            "receipt": f"user{user_id}_plan{plan_id}_{int(datetime.utcnow().timestamp())}",
            "notes": {
                "user_id": str(user_id),
                "plan_id": str(plan_id),
                "goal_id": str(plan["goal_id"]),
            },
        })
    except Exception as e:
        print(f"[razorpay] create-order failed: {e}")
        return jsonify(success=False, message="Failed to create order"), 500

    return jsonify(
        success=True,
        order_id=order["id"],
        amount=amount_paise,
        currency=order["currency"],
        key_id=key_id,
        plan_id=plan["id"],
        plan_name=plan["name"],
    )


# ═══════════════════════════════════════════════════════════════
# PAYMENT — VERIFY + ACTIVATE SUBSCRIPTION
# ═══════════════════════════════════════════════════════════════

@api_auth_bp.route("/payment/verify", methods=["POST"])
@api_login_required
def api_verify_payment():
    import os
    import hmac
    import hashlib
    from datetime import datetime, timedelta

    user_id = g.user_id
    data = request.get_json() or {}

    order_id = data.get("razorpay_order_id")
    payment_id = data.get("razorpay_payment_id")
    signature = data.get("razorpay_signature")
    plan_id = data.get("plan_id")

    if not all([order_id, payment_id, signature, plan_id]):
        return jsonify(success=False, message="Missing fields"), 400

    secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not secret:
        return jsonify(success=False, message="Payment not configured"), 500

    # 1. Verify signature
    body = f"{order_id}|{payment_id}".encode()
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        print(f"[razorpay] signature mismatch for {payment_id}")
        return jsonify(success=False, message="Invalid signature"), 400

    with db_cursor() as cur:
        # 2. Fetch plan
        cur.execute("""
            SELECT id, goal_id, duration_days FROM plans WHERE id = %s
        """, (plan_id,))
        plan = cur.fetchone()
        if not plan:
            return jsonify(success=False, message="Plan not found"), 404

        # 3. Idempotency — if already recorded, return success
        cur.execute("""
            SELECT id FROM subscriptions
            WHERE user_id = %s AND provider_sub_id = %s
        """, (user_id, payment_id))
        if cur.fetchone():
            return jsonify(success=True, message="Already recorded")

        # 4. Compute period — extend from current active sub
        now = datetime.utcnow()
        cur.execute("""
            SELECT MAX(current_period_end) AS latest
            FROM subscriptions
            WHERE user_id = %s AND goal_id = %s
              AND status IN ('active','trialing','past_due','canceling')
        """, (user_id, plan["goal_id"]))
        row = cur.fetchone()
        latest_end = row["latest"] if row else None

        start = latest_end if latest_end and latest_end > now else now
        end = start + timedelta(days=plan["duration_days"])

        # 5. Insert subscription
        cur.execute("""
            INSERT INTO subscriptions
                (user_id, plan_id, goal_id, status,
                 current_period_start, current_period_end,
                 payment_provider, provider_sub_id)
            VALUES (%s, %s, %s, 'active', %s, %s, 'razorpay', %s)
        """, (user_id, plan_id, plan["goal_id"], start, end, payment_id))

    return jsonify(
        success=True,
        message="Subscription activated",
        redirect="/home",
    )


# ═══════════════════════════════════════════════════════════════
# MY SUBSCRIPTIONS — for the "My Subscriptions" page
# ═══════════════════════════════════════════════════════════════

@api_auth_bp.route("/subscriptions", methods=["GET"])
@api_login_required
def api_my_subscriptions():
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT
                s.id, s.status, s.current_period_start, s.current_period_end,
                s.payment_provider, s.created_at,
                p.name AS plan_name, p.price, p.currency, p.duration_days,
                g.name AS goal_name
            FROM subscriptions s
            JOIN plans p ON s.plan_id = p.id
            JOIN goals g ON s.goal_id = g.id
            WHERE s.user_id = %s
            ORDER BY s.created_at DESC
        """, (user_id,))
        subs = cur.fetchall()

    return jsonify(
        success=True,
        subscriptions=[
            {
                "id": s["id"],
                "status": s["status"],
                "plan_name": s["plan_name"],
                "goal_name": s["goal_name"],
                "price": float(s["price"]),
                "currency": s["currency"],
                "duration_days": s["duration_days"],
                "current_period_start": s["current_period_start"].isoformat() if s["current_period_start"] else None,
                "current_period_end": s["current_period_end"].isoformat() if s["current_period_end"] else None,
                "payment_provider": s["payment_provider"],
            }
            for s in subs
        ],
    )