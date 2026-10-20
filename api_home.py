# api_home.py
from flask import Blueprint, jsonify, g, request
from db import db_cursor
from access import has_access, topic_is_completed
from api_auth import api_login_required

api_home_bp = Blueprint("api_home", __name__, url_prefix="/api")


# ═══════════════════════════════════════════════════════════════
# HOME
# ═══════════════════════════════════════════════════════════════
@api_home_bp.route("/home")
@api_login_required
def api_home():
    """Return the current user's home data as JSON."""
    user_id = g.user_id

    with db_cursor() as cur:
        # 1. Load user + goal
        cur.execute("""
            SELECT
                u.first_name,
                u.current_goal_id,
                g.name AS goal_name
            FROM users u
            LEFT JOIN goals g ON u.current_goal_id = g.id
            WHERE u.id = %s
        """, (user_id,))
        user = cur.fetchone()

        # 2. No goal selected yet?
        if not user or not user["current_goal_id"]:
            return jsonify(
                success=True,
                first_name=(user or {}).get("first_name") or "there",
                goal_name=None,
                subjects=[],
            )

        # 3. Load subjects with topic progress
        cur.execute("""
            SELECT
                s.id            AS subject_id,
                s.name          AS subject_name,
                COUNT(t.id)     AS total_topics,
                COUNT(p.id) FILTER (WHERE p.status = 'completed') AS completed_topics
            FROM subjects s
            LEFT JOIN chapters c ON c.subject_id = s.id
            LEFT JOIN topics t
                ON t.chapter_id = c.id
               AND t.context IN ('practice', 'both')
            LEFT JOIN user_topic_progress p
                ON p.topic_id = t.id AND p.user_id = %s
            WHERE s.goal_id = %s
            GROUP BY s.id, s.name
            ORDER BY s.id
        """, (user_id, user["current_goal_id"]))
        subjects = cur.fetchall()

    subjects_list = [
        {
            "subject_id": s["subject_id"],
            "subject_name": s["subject_name"],
            "total_topics": s["total_topics"],
            "completed_topics": s["completed_topics"],
        }
        for s in subjects
    ]

    return jsonify(
        success=True,
        first_name=user["first_name"] or "there",
        goal_name=user["goal_name"],
        subjects=subjects_list,
    )


# ═══════════════════════════════════════════════════════════════
# GOALS
# ═══════════════════════════════════════════════════════════════
@api_home_bp.route("/goals")
@api_login_required
def api_goals():
    with db_cursor() as cur:
        cur.execute("SELECT id, name FROM goals ORDER BY id")
        goals = cur.fetchall()

    return jsonify(
        success=True,
        goals=[{"id": g["id"], "name": g["name"]} for g in goals],
    )


@api_home_bp.route("/goals/select", methods=["POST"])
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

    return jsonify(success=True)


# ═══════════════════════════════════════════════════════════════
# USER — set name
# ═══════════════════════════════════════════════════════════════
@api_home_bp.route("/user/name", methods=["POST"])
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
            "UPDATE users SET first_name = %s, last_name = %s WHERE id = %s",
            (first_name, last_name or None, user_id),
        )

    return jsonify(success=True)


# ═══════════════════════════════════════════════════════════════
# SUBJECT → CHAPTERS → TOPICS
# ═══════════════════════════════════════════════════════════════
@api_home_bp.route("/subjects/<int:subject_id>/topics")
@api_login_required
def api_subject_topics(subject_id):
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT s.id, s.name, s.goal_id, g.name AS goal_name
            FROM subjects s
            JOIN goals g ON s.goal_id = g.id
            WHERE s.id = %s
        """, (subject_id,))
        subject = cur.fetchone()
        if not subject:
            return jsonify(success=False, message="Subject not found"), 404

        cur.execute("""
            SELECT id, name
            FROM chapters
            WHERE subject_id = %s
            ORDER BY position, id
        """, (subject_id,))
        chapters = cur.fetchall()

        chapter_ids = [c["id"] for c in chapters]
        topics = []
        if chapter_ids:
            cur.execute("""
                SELECT id, chapter_id, name, access_level
                FROM topics
                WHERE chapter_id = ANY(%s)
                  AND context IN ('practice', 'both')
                ORDER BY chapter_id, id
            """, (chapter_ids,))
            topics = cur.fetchall()

        topic_ids = [t["id"] for t in topics]
        progress = {}
        if topic_ids:
            cur.execute("""
                SELECT topic_id, status, correct_count, attempted_count
                FROM user_topic_progress
                WHERE user_id = %s AND topic_id = ANY(%s)
            """, (user_id, topic_ids))
            progress = {row["topic_id"]: row for row in cur.fetchall()}

    user_has_access = has_access(user_id, subject["goal_id"])

    topics_by_chapter = {}
    for t in topics:
        topics_by_chapter.setdefault(t["chapter_id"], []).append(t)

    chapter_payloads = []
    for c in chapters:
        c_topics = []
        for t in topics_by_chapter.get(c["id"], []):
            locked = (t["access_level"] == "paid") and not user_has_access
            p = progress.get(t["id"])
            c_topics.append({
                "id": t["id"],
                "name": t["name"],
                "access_level": t["access_level"],
                "locked": locked,
                "status": p["status"] if p else "not_started",
                "correct_count": p["correct_count"] if p else 0,
                "attempted_count": p["attempted_count"] if p else 0,
            })
        chapter_payloads.append({
            "id": c["id"],
            "name": c["name"],
            "topics": c_topics,
        })

    return jsonify(
        success=True,
        subject={
            "id": subject["id"],
            "name": subject["name"],
            "goal_id": subject["goal_id"],
            "goal_name": subject["goal_name"],
        },
        chapters=chapter_payloads,
    )


# ═══════════════════════════════════════════════════════════════
# TOPIC → START (access check + completion check)
# ═══════════════════════════════════════════════════════════════
@api_home_bp.route("/topics/<int:topic_id>/start")
@api_login_required
def api_topic_start(topic_id):
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT t.id, t.name, t.access_level,
                   s.goal_id, g.name AS goal_name
            FROM topics t
            JOIN chapters c ON t.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            JOIN goals g ON s.goal_id = g.id
            WHERE t.id = %s
        """, (topic_id,))
        topic = cur.fetchone()
        if not topic:
            return jsonify(success=False, message="Topic not found"), 404

    user_has_access = has_access(user_id, topic["goal_id"])
    if topic["access_level"] == "paid" and not user_has_access:
        return jsonify(success=False, message="Subscription required"), 403

    completed = topic_is_completed(user_id, topic_id)

    return jsonify(
        success=True,
        topic={
            "id": topic["id"],
            "name": topic["name"],
            "access_level": topic["access_level"],
            "goal_id": topic["goal_id"],
            "goal_name": topic["goal_name"],
        },
        completed=completed,
        next_mode="review" if completed else "questions",
    )


# ═══════════════════════════════════════════════════════════════
# TOPIC → QUESTIONS (landing info)
# ═══════════════════════════════════════════════════════════════
@api_home_bp.route("/topics/<int:topic_id>/questions")
@api_login_required
def api_topic_questions_info(topic_id):
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT t.id, t.name, t.access_level,
                   s.goal_id, g.name AS goal_name
            FROM topics t
            JOIN chapters c ON t.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            JOIN goals g ON s.goal_id = g.id
            WHERE t.id = %s
        """, (topic_id,))
        topic = cur.fetchone()
        if not topic:
            return jsonify(success=False, message="Topic not found"), 404

        user_has_access = has_access(user_id, topic["goal_id"])
        if topic["access_level"] == "paid" and not user_has_access:
            return jsonify(success=False, message="Subscription required"), 403

        completed = topic_is_completed(user_id, topic_id)

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM questions
            WHERE topic_id = %s
              AND context IN ('practice', 'both')
        """, (topic_id,))
        question_count = cur.fetchone()["total"]

        cur.execute("""
            SELECT 1 FROM user_answers ua
            JOIN questions q ON ua.question_id = q.id
            WHERE ua.user_id = %s
              AND q.topic_id = %s
              AND ua.context = 'practice'
            LIMIT 1
        """, (user_id, topic_id))
        has_past = cur.fetchone() is not None

    return jsonify(
        success=True,
        topic={
            "id": topic["id"],
            "name": topic["name"],
            "access_level": topic["access_level"],
            "goal_id": topic["goal_id"],
            "goal_name": topic["goal_name"],
        },
        completed=completed,
        question_count=question_count,
        has_past_attempts=has_past,
        next_mode="review" if completed else "quiz",
        quiz_mode="resume" if has_past else "fresh",
    )


# ═══════════════════════════════════════════════════════════════
# TOPIC → FRESH QUIZ
# ═══════════════════════════════════════════════════════════════
@api_home_bp.route("/topics/<int:topic_id>/quiz/fresh")
@api_login_required
def api_topic_quiz_fresh(topic_id):
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT t.id, t.name, t.access_level,
                   s.goal_id, g.name AS goal_name
            FROM topics t
            JOIN chapters c ON t.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            JOIN goals g ON s.goal_id = g.id
            WHERE t.id = %s
        """, (topic_id,))
        topic = cur.fetchone()
        if not topic:
            return jsonify(success=False, message="Topic not found"), 404

        user_has_access = has_access(user_id, topic["goal_id"])
        if topic["access_level"] == "paid" and not user_has_access:
            return jsonify(success=False, message="Subscription required"), 403

        if topic_is_completed(user_id, topic_id):
            return jsonify(
                success=False,
                message="Topic already completed",
                redirect_review=True,
            ), 409

        cur.execute("""
            SELECT id, text, option_a, option_b, option_c, option_d, image_path
            FROM questions
            WHERE topic_id = %s
              AND context IN ('practice', 'both')
            ORDER BY id
        """, (topic_id,))
        questions = cur.fetchall()

        cur.execute("""
            SELECT question_id FROM user_bookmarks
            WHERE user_id = %s
              AND question_id IN (
                  SELECT id FROM questions WHERE topic_id = %s
              )
        """, (user_id, topic_id))
        bookmarked_ids = [row["question_id"] for row in cur.fetchall()]

    return jsonify(
        success=True,
        mode="fresh",
        topic={
            "id": topic["id"],
            "name": topic["name"],
            "access_level": topic["access_level"],
            "goal_id": topic["goal_id"],
            "goal_name": topic["goal_name"],
        },
        questions=[
            {
                "id": q["id"],
                "text": q["text"],
                "option_a": q["option_a"],
                "option_b": q["option_b"],
                "option_c": q["option_c"],
                "option_d": q["option_d"],
                "image_path": q["image_path"],
            }
            for q in questions
        ],
        past_answers={},
        start_index=0,
        bookmarked_ids=bookmarked_ids,
    )


# ═══════════════════════════════════════════════════════════════
# TOPIC → RESUME QUIZ
# ═══════════════════════════════════════════════════════════════
@api_home_bp.route("/topics/<int:topic_id>/quiz/resume")
@api_login_required
def api_topic_quiz_resume(topic_id):
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT t.id, t.name, t.access_level,
                   s.goal_id, g.name AS goal_name
            FROM topics t
            JOIN chapters c ON t.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            JOIN goals g ON s.goal_id = g.id
            WHERE t.id = %s
        """, (topic_id,))
        topic = cur.fetchone()
        if not topic:
            return jsonify(success=False, message="Topic not found"), 404

        user_has_access = has_access(user_id, topic["goal_id"])
        if topic["access_level"] == "paid" and not user_has_access:
            return jsonify(success=False, message="Subscription required"), 403

        if topic_is_completed(user_id, topic_id):
            return jsonify(
                success=False,
                message="Topic already completed",
                redirect_review=True,
            ), 409

        cur.execute("""
            SELECT id, text, option_a, option_b, option_c, option_d, image_path
            FROM questions
            WHERE topic_id = %s
              AND context IN ('practice', 'both')
            ORDER BY id
        """, (topic_id,))
        questions = cur.fetchall()

        cur.execute("""
            SELECT DISTINCT ON (ua.question_id)
                ua.question_id,
                ua.selected_option,
                ua.is_correct,
                q.correct_option,
                q.explanation,
                q.explanation_image_path
            FROM user_answers ua
            JOIN questions q ON ua.question_id = q.id
            WHERE ua.user_id = %s
              AND q.topic_id = %s
              AND ua.context = 'practice'
            ORDER BY ua.question_id, ua.answered_at DESC
        """, (user_id, topic_id))
        rows = cur.fetchall()

        cur.execute("""
            SELECT question_id FROM user_bookmarks
            WHERE user_id = %s
              AND question_id IN (
                  SELECT id FROM questions WHERE topic_id = %s
              )
        """, (user_id, topic_id))
        bookmarked_ids = [row["question_id"] for row in cur.fetchall()]

    past_answers = {
        str(r["question_id"]): {
            "selected": r["selected_option"],
            "is_correct": r["is_correct"],
            "correct_option": r["correct_option"],
            "explanation": r["explanation"],
            "explanation_image_path": r["explanation_image_path"],
        }
        for r in rows
    }

    answered_ids = {int(k) for k in past_answers.keys()}
    start_index = 0
    for i, q in enumerate(questions):
        if q["id"] not in answered_ids:
            start_index = i
            break
    else:
        start_index = len(questions) - 1 if questions else 0

    return jsonify(
        success=True,
        mode="resume",
        topic={
            "id": topic["id"],
            "name": topic["name"],
            "access_level": topic["access_level"],
            "goal_id": topic["goal_id"],
            "goal_name": topic["goal_name"],
        },
        questions=[
            {
                "id": q["id"],
                "text": q["text"],
                "option_a": q["option_a"],
                "option_b": q["option_b"],
                "option_c": q["option_c"],
                "option_d": q["option_d"],
                "image_path": q["image_path"],
            }
            for q in questions
        ],
        past_answers=past_answers,
        start_index=start_index,
        bookmarked_ids=bookmarked_ids,
    )


# ═══════════════════════════════════════════════════════════════
# PRACTICE → SUBMIT ANSWER
# ═══════════════════════════════════════════════════════════════
@api_home_bp.route("/practice/answer", methods=["POST"])
@api_login_required
def api_practice_answer():
    user_id = g.user_id
    data = request.get_json() or {}
    question_id = data.get("question_id")
    selected_option = data.get("selected_option")

    if not question_id:
        return jsonify(success=False, message="question_id required"), 400
    if selected_option not in ("A", "B", "C", "D"):
        return jsonify(success=False, message="Invalid option"), 400

    with db_cursor() as cur:
        cur.execute("""
            SELECT q.id, q.topic_id, q.correct_option, q.explanation,
                   q.explanation_image_path, s.goal_id
            FROM questions q
            JOIN topics t ON q.topic_id = t.id
            JOIN chapters c ON t.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            WHERE q.id = %s
        """, (question_id,))
        question = cur.fetchone()
        if not question:
            return jsonify(success=False, message="Question not found"), 404

        user_has_access = has_access(user_id, question["goal_id"])
        cur.execute(
            "SELECT access_level FROM topics WHERE id = %s",
            (question["topic_id"],),
        )
        topic = cur.fetchone()
        if topic["access_level"] == "paid" and not user_has_access:
            return jsonify(success=False, message="Subscription required"), 403

        is_correct = (selected_option == question["correct_option"])

        cur.execute("""
            INSERT INTO user_answers
                (user_id, question_id, selected_option, is_correct, context)
            VALUES (%s, %s, %s, %s, 'practice')
        """, (user_id, question_id, selected_option, is_correct))

    return jsonify(
        success=True,
        is_correct=is_correct,
        selected_option=selected_option,
        correct_option=question["correct_option"],
        explanation=question["explanation"],
        explanation_image_path=question["explanation_image_path"],
    )


# ═══════════════════════════════════════════════════════════════
# PRACTICE → COMPLETE TOPIC
# ═══════════════════════════════════════════════════════════════
@api_home_bp.route("/practice/complete", methods=["POST"])
@api_login_required
def api_practice_complete():
    user_id = g.user_id
    data = request.get_json() or {}
    topic_id = data.get("topic_id")

    if not topic_id:
        return jsonify(success=False, message="topic_id required"), 400

    with db_cursor() as cur:
        cur.execute("""
            SELECT t.id, t.name, t.access_level, s.goal_id
            FROM topics t
            JOIN chapters c ON t.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            WHERE t.id = %s
        """, (topic_id,))
        topic = cur.fetchone()
        if not topic:
            return jsonify(success=False, message="Topic not found"), 404

        user_has_access = has_access(user_id, topic["goal_id"])
        if topic["access_level"] == "paid" and not user_has_access:
            return jsonify(success=False, message="Subscription required"), 403

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE ua.is_correct) AS correct_count,
                COUNT(*) AS attempted_count
            FROM user_answers ua
            JOIN questions q ON ua.question_id = q.id
            WHERE ua.user_id = %s
              AND q.topic_id = %s
              AND ua.context = 'practice'
        """, (user_id, topic_id))
        counts = cur.fetchone()

        correct_count = counts["correct_count"] or 0
        attempted_count = counts["attempted_count"] or 0

        cur.execute("""
            INSERT INTO user_topic_progress
                (user_id, topic_id, status, correct_count, attempted_count, completed_at)
            VALUES (%s, %s, 'completed', %s, %s, NOW())
            ON CONFLICT (user_id, topic_id)
            DO UPDATE SET
                status = 'completed',
                correct_count = EXCLUDED.correct_count,
                attempted_count = EXCLUDED.attempted_count,
                completed_at = NOW()
        """, (user_id, topic_id, correct_count, attempted_count))

    return jsonify(
        success=True,
        summary={
            "correct": correct_count,
            "attempted": attempted_count,
        },
    )


# ═══════════════════════════════════════════════════════════════
# TOPIC → SUBMIT SUMMARY
# ═══════════════════════════════════════════════════════════════
@api_home_bp.route("/topics/<int:topic_id>/submit")
@api_login_required
def api_topic_submit(topic_id):
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT t.id, t.name, t.access_level,
                   s.id AS subject_id, s.goal_id, g.name AS goal_name
            FROM topics t
            JOIN chapters c ON t.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            JOIN goals g ON s.goal_id = g.id
            WHERE t.id = %s
        """, (topic_id,))
        topic = cur.fetchone()
        if not topic:
            return jsonify(success=False, message="Topic not found"), 404

        user_has_access = has_access(user_id, topic["goal_id"])
        if topic["access_level"] == "paid" and not user_has_access:
            return jsonify(success=False, message="Subscription required"), 403

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE ua.is_correct) AS correct_count,
                COUNT(*) FILTER (WHERE NOT ua.is_correct) AS wrong_count,
                COUNT(*) AS attempted_count
            FROM user_answers ua
            JOIN questions q ON ua.question_id = q.id
            WHERE ua.user_id = %s
              AND q.topic_id = %s
              AND ua.context = 'practice'
        """, (user_id, topic_id))
        counts = cur.fetchone()

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM questions
            WHERE topic_id = %s
              AND context IN ('practice', 'both')
        """, (topic_id,))
        total_questions = cur.fetchone()["total"]

    return jsonify(
        success=True,
        topic={
            "id": topic["id"],
            "name": topic["name"],
            "subject_id": topic["subject_id"],
            "goal_id": topic["goal_id"],
            "goal_name": topic["goal_name"],
        },
        correct_count=counts["correct_count"] or 0,
        wrong_count=counts["wrong_count"] or 0,
        attempted_count=counts["attempted_count"] or 0,
        total_questions=total_questions,
    )


# ═══════════════════════════════════════════════════════════════
# TOPIC → REVIEW SUMMARY
# ═══════════════════════════════════════════════════════════════
@api_home_bp.route("/topics/<int:topic_id>/review")
@api_login_required
def api_topic_review(topic_id):
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT t.id, t.name, t.access_level,
                   s.id AS subject_id, s.goal_id, g.name AS goal_name
            FROM topics t
            JOIN chapters c ON t.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            JOIN goals g ON s.goal_id = g.id
            WHERE t.id = %s
        """, (topic_id,))
        topic = cur.fetchone()
        if not topic:
            return jsonify(success=False, message="Topic not found"), 404

        user_has_access = has_access(user_id, topic["goal_id"])
        if topic["access_level"] == "paid" and not user_has_access:
            return jsonify(success=False, message="Subscription required"), 403

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE ua.is_correct) AS correct_count,
                COUNT(*) FILTER (WHERE NOT ua.is_correct) AS wrong_count,
                COUNT(*) AS attempted_count
            FROM user_answers ua
            JOIN questions q ON ua.question_id = q.id
            WHERE ua.user_id = %s
              AND q.topic_id = %s
              AND ua.context = 'practice'
        """, (user_id, topic_id))
        counts = cur.fetchone()

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM questions
            WHERE topic_id = %s
              AND context IN ('practice', 'both')
        """, (topic_id,))
        total_questions = cur.fetchone()["total"]

    return jsonify(
        success=True,
        topic={
            "id": topic["id"],
            "name": topic["name"],
            "subject_id": topic["subject_id"],
            "goal_id": topic["goal_id"],
            "goal_name": topic["goal_name"],
        },
        correct_count=counts["correct_count"] or 0,
        wrong_count=counts["wrong_count"] or 0,
        attempted_count=counts["attempted_count"] or 0,
        total_questions=total_questions,
    )


# ═══════════════════════════════════════════════════════════════
# TOPIC → REVIEW QUESTIONS
# ═══════════════════════════════════════════════════════════════
@api_home_bp.route("/topics/<int:topic_id>/review/questions")
@api_login_required
def api_topic_review_questions(topic_id):
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT t.id, t.name, t.access_level,
                   s.id AS subject_id, s.goal_id
            FROM topics t
            JOIN chapters c ON t.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            WHERE t.id = %s
        """, (topic_id,))
        topic = cur.fetchone()
        if not topic:
            return jsonify(success=False, message="Topic not found"), 404

        user_has_access = has_access(user_id, topic["goal_id"])
        if topic["access_level"] == "paid" and not user_has_access:
            return jsonify(success=False, message="Subscription required"), 403

        cur.execute("""
            SELECT
                q.id AS question_id,
                q.text,
                q.option_a,
                q.option_b,
                q.option_c,
                q.option_d,
                q.correct_option,
                q.explanation,
                q.image_path,
                q.explanation_image_path,
                ua.selected_option,
                ua.is_correct
            FROM questions q
            LEFT JOIN (
                SELECT DISTINCT ON (question_id)
                    question_id, selected_option, is_correct
                FROM user_answers
                WHERE user_id = %s AND context = 'practice'
                ORDER BY question_id, answered_at DESC
            ) ua ON ua.question_id = q.id
            WHERE q.topic_id = %s
              AND q.context IN ('practice', 'both')
            ORDER BY q.id
        """, (user_id, topic_id))
        rows = cur.fetchall()

        cur.execute("""
            SELECT question_id FROM user_bookmarks
            WHERE user_id = %s
              AND question_id IN (
                  SELECT id FROM questions WHERE topic_id = %s
              )
        """, (user_id, topic_id))
        bookmarked_ids = [r["question_id"] for r in cur.fetchall()]

    return jsonify(
        success=True,
        topic={
            "id": topic["id"],
            "name": topic["name"],
            "subject_id": topic["subject_id"],
            "goal_id": topic["goal_id"],
        },
        questions=[
            {
                "id": r["question_id"],
                "text": r["text"],
                "option_a": r["option_a"],
                "option_b": r["option_b"],
                "option_c": r["option_c"],
                "option_d": r["option_d"],
                "correct_option": r["correct_option"],
                "explanation": r["explanation"],
                "image_path": r["image_path"],
                "explanation_image_path": r["explanation_image_path"],
                "user_answer": r["selected_option"],
                "is_correct": r["is_correct"],
            }
            for r in rows
        ],
        bookmarked_ids=bookmarked_ids,
    )


# ═══════════════════════════════════════════════════════════════
# BOOKMARKS — add / remove (practice side)
# ═══════════════════════════════════════════════════════════════
@api_home_bp.route("/bookmarks", methods=["POST"])
@api_login_required
def api_add_bookmark():
    user_id = g.user_id
    data = request.get_json() or {}
    question_id = data.get("question_id")
    source = data.get("source", "practice")

    if not question_id:
        return jsonify(success=False, message="question_id required"), 400

    with db_cursor() as cur:
        cur.execute("SELECT id FROM questions WHERE id = %s", (question_id,))
        if not cur.fetchone():
            return jsonify(success=False, message="Question not found"), 404

        cur.execute("""
            INSERT INTO user_bookmarks (user_id, question_id, source)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, question_id) DO NOTHING
        """, (user_id, question_id, source))

    return jsonify(success=True, bookmarked=True)


@api_home_bp.route("/bookmarks/<int:question_id>", methods=["DELETE"])
@api_login_required
def api_remove_bookmark(question_id):
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            DELETE FROM user_bookmarks
            WHERE user_id = %s AND question_id = %s
        """, (user_id, question_id))

    return jsonify(success=True, bookmarked=False)