# payment.py
#
# Razorpay payment integration.
# Handles: create order, verify signature, insert subscription.

import os
import hmac
import hashlib
from datetime import datetime, timedelta



from dotenv import load_dotenv
load_dotenv() 

import razorpay
from flask import Blueprint, request, jsonify, session, redirect
from db import db_cursor

payment_bp = Blueprint("payment", __name__, url_prefix="/payment")


# ─────────────────────────────────────────────────────────────
# Razorpay client (lazy init so missing env vars don't crash app)
# ─────────────────────────────────────────────────────────────
def get_client():
    key = os.environ.get("RAZORPAY_KEY_ID")
    secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not key or not secret:
        return None
    return razorpay.Client(auth=(key, secret))


# ═══════════════════════════════════════════════════════════════
# 1. CREATE ORDER
# ═══════════════════════════════════════════════════════════════
@payment_bp.route("/create-order", methods=["POST"])
def create_order():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, message="Not logged in"), 401

    data = request.get_json() or {}
    plan_id = data.get("plan_id")

    if not plan_id:
        return jsonify(success=False, message="plan_id required"), 400

    # Fetch plan from DB — NEVER trust amount from frontend
    with db_cursor() as cur:
        cur.execute("""
            SELECT id, goal_id, name, duration_days, price, currency
            FROM plans WHERE id = %s
        """, (plan_id,))
        plan = cur.fetchone()

    if not plan:
        return jsonify(success=False, message="Plan not found"), 404

    client = get_client()
    if not client:
        return jsonify(success=False, message="Payment not configured"), 500

    # Razorpay expects amount in paise (smallest currency unit)
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
        key_id=os.environ.get("RAZORPAY_KEY_ID"),
        plan_name=plan["name"],
        user_email=None,  # can fill if you have it
    )


# ═══════════════════════════════════════════════════════════════
# 2. VERIFY PAYMENT + INSERT SUBSCRIPTION
# ═══════════════════════════════════════════════════════════════
@payment_bp.route("/verify", methods=["POST"])
def verify_payment():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, message="Not logged in"), 401

    data = request.get_json() or {}
    order_id = data.get("razorpay_order_id")
    payment_id = data.get("razorpay_payment_id")
    signature = data.get("razorpay_signature")
    plan_id = data.get("plan_id")

    if not all([order_id, payment_id, signature, plan_id]):
        return jsonify(success=False, message="Missing fields"), 400

    # 1. Verify signature
    secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not secret:
        return jsonify(success=False, message="Payment not configured"), 500

    body = f"{order_id}|{payment_id}".encode()
    expected = hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        print(f"[razorpay] signature mismatch for payment {payment_id}")
        return jsonify(success=False, message="Invalid signature"), 400

    # 2. Fetch plan to compute end date
    with db_cursor() as cur:
        cur.execute("""
            SELECT id, goal_id, duration_days
            FROM plans WHERE id = %s
        """, (plan_id,))
        plan = cur.fetchone()

        if not plan:
            return jsonify(success=False, message="Plan not found"), 404

        # 3. Idempotency — skip if this payment_id is already recorded
        cur.execute("""
            SELECT id FROM subscriptions
            WHERE user_id = %s AND provider_sub_id = %s
        """, (user_id, payment_id))
        if cur.fetchone():
            return jsonify(success=True, message="Already recorded")

        # 4. Compute period — extend from current active sub if any
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
# 3. LIST ACTIVE SUBSCRIPTIONS (for "My Subscription" page later)
# ═══════════════════════════════════════════════════════════════
@payment_bp.route("/my-subscriptions")
def my_subscriptions():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

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

    return jsonify(success=True, subscriptions=[dict(s) for s in subs])