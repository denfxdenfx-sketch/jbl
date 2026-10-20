# access.py
from flask import g
from db import db_cursor


def has_access(user_id, goal_id):
    """
    Returns True if the user has an active subscription for this goal.
    Cached per-request using Flask's `g`.
    """
    if not user_id or not goal_id:
        return False

    cache_key = f"access_{user_id}_{goal_id}"
    if hasattr(g, cache_key):
        return getattr(g, cache_key)

    with db_cursor() as cur:
        cur.execute("""
            SELECT 1 FROM subscriptions
            WHERE user_id = %s
              AND goal_id = %s
              AND status IN ('active', 'trialing', 'past_due', 'canceling')
              AND current_period_start <= NOW()
              AND current_period_end > NOW()
            LIMIT 1
        """, (user_id, goal_id))
        result = cur.fetchone() is not None

    setattr(g, cache_key, result)
    return result


def get_topic_access(user_id, goal_id, topics):
    """
    Adds a 'locked' key to each topic dict.

    A topic is locked if:
      - access_level is 'paid'
      - AND the user does NOT have an active subscription for the goal

    Free topics are never locked.
    """
    user_has_access = has_access(user_id, goal_id)

    result = []
    for t in topics:
        is_paid = t["access_level"] == "paid"
        is_locked = is_paid and not user_has_access
        result.append({
            **t,
            "locked": is_locked,
        })
    return result


def completed_topic_ids(user_id, subject_id):
    """
    Returns a set of topic IDs the user has completed
    within the given subject.
    """
    with db_cursor() as cur:
        cur.execute("""
            SELECT p.topic_id
            FROM user_topic_progress p
            JOIN topics t ON p.topic_id = t.id
            WHERE p.user_id = %s
              AND t.subject_id = %s
              AND p.status = 'completed'
        """, (user_id, subject_id))
        return {row["topic_id"] for row in cur.fetchall()}
    

def topic_is_completed(user_id, topic_id):
    """Returns True if the user has completed this specific topic."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT 1 FROM user_topic_progress
            WHERE user_id = %s
              AND topic_id = %s
              AND status = 'completed'
            LIMIT 1
        """, (user_id, topic_id))
        return cur.fetchone() is not None


# In access.py (or wherever you keep helpers)

def get_test_access(user_id, goal_id, tests):
    """
    Adds a 'locked' key to each test dict.
    A test is locked if access_level='paid' and the user has no subscription.
    Free tests are never locked.
    """
    user_has_access = has_access(user_id, goal_id)

    result = []
    for t in tests:
        is_paid = t["access_level"] == "paid"
        is_locked = is_paid and not user_has_access
        result.append({
            **t,
            "locked": is_locked,
        })
    return result


def completed_test_ids(user_id, goal_id):
    """
    Returns a set of test IDs where the user has at least one submitted attempt.
    """
    with db_cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ta.test_id
            FROM test_attempts ta
            JOIN tests t ON ta.test_id = t.id
            WHERE ta.user_id = %s
              AND t.goal_id = %s
              AND ta.status = 'submitted'
        """, (user_id, goal_id))
        return {row["test_id"] for row in cur.fetchall()}


# In access.py

def test_is_completed(user_id, test_id):
    """
    Returns True if the user has at least one submitted attempt for this test.
    Returns False otherwise.
    """
    with db_cursor() as cur:
        cur.execute("""
            SELECT 1 FROM test_attempts
            WHERE user_id = %s
              AND test_id = %s
              AND status = 'submitted'
            LIMIT 1
        """, (user_id, test_id))
        return cur.fetchone() is not None
    


    #access related stufffsss


def qbank_topic_is_completed(user_id, qbank_topic_id):
    """True if the user has completed this qbank topic."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT 1 FROM qbank_topic_completion
            WHERE user_id = %s
              AND qbank_topic_id = %s
            LIMIT 1
        """, (user_id, qbank_topic_id))
        return cur.fetchone() is not None


def completed_qbank_topic_ids(user_id, subject_id):
    """Set of qbank topic IDs completed by the user under this subject."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT c.qbank_topic_id
            FROM qbank_topic_completion c
            JOIN qbank_topics t ON c.qbank_topic_id = t.id
            JOIN chapters ch   ON t.chapter_id      = ch.id
            WHERE c.user_id = %s
              AND ch.subject_id = %s
        """, (user_id, subject_id))
        return {row["qbank_topic_id"] for row in cur.fetchall()}    





