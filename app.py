from flask import Flask, render_template, session, redirect, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
from db import db_cursor
from flask_cors import CORS  
import os# with the other imports at the top

app = Flask(__name__)
app.secret_key = "change-this-to-a-random-string"
CORS(app)                            # right after app = Flask(__name__)


DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "database": os.environ.get("DB_NAME", "myapp_db"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", "br09s3765"),
    "port": os.environ.get("DB_PORT", "5432"),
}


def get_db():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    return conn, cur


def close_db(conn, cur):
    if cur: cur.close()
    if conn: conn.close()


# ─────────────────────────────────────────────────────────────
# Register blueprints
# ─────────────────────────────────────────────────────────────
from auth import auth_bp
app.register_blueprint(auth_bp)

from bookmark import bookmark_bp
app.register_blueprint(bookmark_bp)

from test import test_bp
app.register_blueprint(test_bp)

from qbank import qbank_bp
app.register_blueprint(qbank_bp)

from api_auth import api_auth_bp
app.register_blueprint(api_auth_bp)


from api_home import api_home_bp
app.register_blueprint(api_home_bp)

from api_qbank import api_qbank_bp
app.register_blueprint(api_qbank_bp)

from api_bookmark import api_bookmark_bp
app.register_blueprint(api_bookmark_bp)

from api_test import api_test_bp
app.register_blueprint(api_test_bp)






from payment import payment_bp
app.register_blueprint(payment_bp)



# ─────────────────────────────────────────────────────────────
# Landing page
# ─────────────────────────────────────────────────────────────
@app.route("/")
def landing():
    return render_template("landing.html")


# ─────────────────────────────────────────────────────────────
# /check — if logged in go to home, else show login
# ─────────────────────────────────────────────────────────────
@app.route("/check")
def check():
    if not session.get("user_id"):
        return render_template("login.html")
    return redirect("/home")


# ─────────────────────────────────────────────────────────────
# /view-plans — if logged in show plans, else show login
# ─────────────────────────────────────────────────────────────
@app.route("/view-plans")
def view_plans():
    user_id = session.get("user_id")
    if not user_id:
        return render_template("login.html")

    with db_cursor() as cur:
        cur.execute("SELECT current_goal_id FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()

        if not user or not user["current_goal_id"]:
            return redirect("/home")

        goal_id = user["current_goal_id"]

        cur.execute("SELECT name FROM goals WHERE id = %s", (goal_id,))
        goal = cur.fetchone()
        if not goal:
            return redirect("/home")

        cur.execute("""
            SELECT id, name, duration_days, price, currency
            FROM plans WHERE goal_id = %s ORDER BY duration_days
        """, (goal_id,))
        plans = cur.fetchall()

    return render_template("plans.html", goal_name=goal["name"], plans=plans)


# ─────────────────────────────────────────────────────────────
# /home
# ─────────────────────────────────────────────────────────────
@app.route("/home")
def home():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    with db_cursor() as cur:
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

        if not user["current_goal_id"]:
            return render_template(
                "home.html",
                first_name=user["first_name"] or "there",
                goal_name=None,
                subjects=[],
            )

        # ← CHANGED: route through chapters
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

    return render_template(
        "home.html",
        first_name=user["first_name"] or "there",
        goal_name=user["goal_name"],
        subjects=subjects,
    )


@app.route("/goals")
def goals_page():
    if not session.get("user_id"):
        return redirect("/login")

    with db_cursor() as cur:
        cur.execute("SELECT id, name FROM goals ORDER BY id")
        goals = cur.fetchall()

    return render_template("goals.html", goals=goals)


@app.route("/goals/select", methods=["POST"])
def select_goal():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, message="Not logged in"), 401

    data = request.get_json() or {}
    goal_id = data.get("goal_id")

    if not goal_id:
        return jsonify(success=False, message="goal_id required"), 400

    with db_cursor() as cur:
        cur.execute("SELECT id FROM goals WHERE id = %s", (goal_id,))
        if not cur.fetchone():
            return jsonify(success=False, message="Goal not found"), 404

        cur.execute("""
            UPDATE users SET current_goal_id = %s WHERE id = %s
        """, (goal_id, user_id))

    return jsonify(success=True, redirect="/name")


@app.route("/name")
def name_page():
    if not session.get("user_id"):
        return redirect("/login")
    return render_template("name.html")


@app.route("/user/set-name", methods=["POST"])
def set_name():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, message="Not logged in"), 401

    data = request.get_json() or {}
    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()

    if not first_name:
        return jsonify(success=False, message="First name required"), 400

    with db_cursor() as cur:
        cur.execute("""
            UPDATE users SET first_name = %s, last_name = %s WHERE id = %s
        """, (first_name, last_name or None, user_id))

    return jsonify(success=True, redirect="/home")


@app.route("/setup-number")
def setup_number():
    if not session.get("user_id"):
        return redirect("/login")
    return render_template("setup_number.html")


from access import has_access, get_topic_access, completed_topic_ids


# ═══════════════════════════════════════════════════════════════
# SUBJECT → CHAPTERS → TOPICS
# ═══════════════════════════════════════════════════════════════
@app.route("/subjects/<int:subject_id>/topics")
def subject_topics(subject_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    with db_cursor() as cur:
        # 1. Load subject + goal
        cur.execute("""
            SELECT s.id, s.name, s.goal_id, g.name AS goal_name
            FROM subjects s
            JOIN goals g ON s.goal_id = g.id
            WHERE s.id = %s
        """, (subject_id,))
        subject = cur.fetchone()

        if not subject:
            return "Subject not found", 404

        # 2. Load chapters for this subject
        cur.execute("""
            SELECT id, name
            FROM chapters
            WHERE subject_id = %s
            ORDER BY position, id
        """, (subject_id,))
        chapters = cur.fetchall()

        # 3. Load topics for those chapters (one query)
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

        # 4. Load progress for those topics (one query)
        topic_ids = [t["id"] for t in topics]
        progress = {}
        if topic_ids:
            cur.execute("""
                SELECT topic_id, status, correct_count, attempted_count
                FROM user_topic_progress
                WHERE user_id = %s AND topic_id = ANY(%s)
            """, (user_id, topic_ids))
            progress = {row["topic_id"]: row for row in cur.fetchall()}

    # 5. Access check
    user_has_access = has_access(user_id, subject["goal_id"])

    # 6. Group topics by chapter
    topics_by_chapter = {}
    for t in topics:
        topics_by_chapter.setdefault(t["chapter_id"], []).append(t)

    # 7. Build the payload
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

    return render_template(
        "topics.html",
        subject=subject,
        chapters=chapter_payloads,
    )


# ═══════════════════════════════════════════════════════════════
# TOPIC → START
# ═══════════════════════════════════════════════════════════════
from access import has_access, topic_is_completed


@app.route("/topics/<int:topic_id>/start")
def start_topic(topic_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    with db_cursor() as cur:
        # ← CHANGED: route through chapters
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
            return "Topic not found", 404

    user_has_access = has_access(user_id, topic["goal_id"])
    if topic["access_level"] == "paid" and not user_has_access:
        return render_template("subscribe.html", topic=topic)

    if topic_is_completed(user_id, topic_id):
        return redirect(f"/topics/{topic_id}/review")

    return redirect(f"/topics/{topic_id}/questions")


# ═══════════════════════════════════════════════════════════════
# TOPIC → QUESTIONS (landing)
# ═══════════════════════════════════════════════════════════════
@app.route("/topics/<int:topic_id>/questions")
def topic_questions(topic_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    with db_cursor() as cur:
        # ← CHANGED: route through chapters
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
            return "Topic not found", 404

        user_has_access = has_access(user_id, topic["goal_id"])
        if topic["access_level"] == "paid" and not user_has_access:
            return redirect(f"/topics/{topic_id}/start")

        if topic_is_completed(user_id, topic_id):
            return redirect(f"/topics/{topic_id}/review")

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM questions
            WHERE topic_id = %s
              AND context IN ('practice', 'both')
        """, (topic_id,))
        question_count = cur.fetchone()["total"]

    return render_template(
        "questions.html",
        topic=topic,
        question_count=question_count,
    )


@app.route("/topics/<int:topic_id>/start-quiz")
def start_quiz(topic_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    with db_cursor() as cur:
        cur.execute("""
            SELECT 1 FROM user_answers ua
            JOIN questions q ON ua.question_id = q.id
            WHERE ua.user_id = %s
              AND q.topic_id = %s
              AND ua.context = 'practice'
            LIMIT 1
        """, (user_id, topic_id))
        has_past = cur.fetchone() is not None

    if has_past:
        return redirect(f"/topics/{topic_id}/quiz/resume")
    else:
        return redirect(f"/topics/{topic_id}/quiz/fresh")


#there wont be any caveat here

# ═══════════════════════════════════════════════════════════════
# TOPIC → FRESH QUIZ
# ═══════════════════════════════════════════════════════════════
@app.route("/topics/<int:topic_id>/quiz/fresh")
def topic_quiz_fresh(topic_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    with db_cursor() as cur:
        # ← CHANGED: route through chapters
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
            return "Topic not found", 404

        user_has_access = has_access(user_id, topic["goal_id"])
        if topic["access_level"] == "paid" and not user_has_access:
            return redirect(f"/topics/{topic_id}/start")

        if topic_is_completed(user_id, topic_id):
            return redirect(f"/topics/{topic_id}/review")

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

    return render_template(
        "quiz.html",
        topic=topic,
        questions=questions,
        past_answers={},
        start_index=0,
        bookmarked_ids=bookmarked_ids,
    )


# ═══════════════════════════════════════════════════════════════
# TOPIC → RESUME QUIZ
# ═══════════════════════════════════════════════════════════════
@app.route("/topics/<int:topic_id>/quiz/resume")
def topic_quiz_resume(topic_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    with db_cursor() as cur:
        # ← CHANGED: route through chapters
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
            return "Topic not found", 404

        user_has_access = has_access(user_id, topic["goal_id"])
        if topic["access_level"] == "paid" and not user_has_access:
            return redirect(f"/topics/{topic_id}/start")

        if topic_is_completed(user_id, topic_id):
            return redirect(f"/topics/{topic_id}/review")

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
        r["question_id"]: {
            "selected": r["selected_option"],
            "is_correct": r["is_correct"],
            "correct_option": r["correct_option"],
            "explanation": r["explanation"],
            "explanation_image_path": r["explanation_image_path"],
        }
        for r in rows
    }

    start_index = 0
    for i, q in enumerate(questions):
        if q["id"] not in past_answers:
            start_index = i
            break
    else:
        start_index = len(questions) - 1 if questions else 0

    return render_template(
        "quiz.html",
        topic=topic,
        questions=questions,
        past_answers=past_answers,
        start_index=start_index,
        bookmarked_ids=bookmarked_ids,
    )


# ═══════════════════════════════════════════════════════════════
# PRACTICE → ANSWER
# ═══════════════════════════════════════════════════════════════
@app.route("/practice/answer", methods=["POST"])
def submit_answer():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, message="Not logged in"), 401

    data = request.get_json() or {}
    question_id = data.get("question_id")
    selected_option = data.get("selected_option")

    if not question_id:
        return jsonify(success=False, message="question_id required"), 400
    if selected_option not in ("A", "B", "C", "D"):
        return jsonify(success=False, message="Invalid option"), 400

    with db_cursor() as cur:
        # ← CHANGED: route through chapters
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
        cur.execute("SELECT access_level FROM topics WHERE id = %s", (question["topic_id"],))
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
# BOOKMARKS
# ═══════════════════════════════════════════════════════════════
@app.route("/bookmarks", methods=["POST"])
def add_bookmark():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, message="Not logged in"), 401

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


@app.route("/bookmarks/<int:question_id>", methods=["DELETE"])
def remove_bookmark(question_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, message="Not logged in"), 401

    with db_cursor() as cur:
        cur.execute("""
            DELETE FROM user_bookmarks
            WHERE user_id = %s AND question_id = %s
        """, (user_id, question_id))

    return jsonify(success=True, bookmarked=False)


# ═══════════════════════════════════════════════════════════════
# PRACTICE → COMPLETE
# ═══════════════════════════════════════════════════════════════
@app.route("/practice/complete", methods=["POST"])
def complete_topic():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, message="Not logged in"), 401

    data = request.get_json() or {}
    topic_id = data.get("topic_id")

    if not topic_id:
        return jsonify(success=False, message="topic_id required"), 400

    with db_cursor() as cur:
        # ← CHANGED: route through chapters
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
            redirect=f"/topics/{topic_id}/submit",
            summary={
                "correct": correct_count,
                "attempted": attempted_count,
            },
        )


# ═══════════════════════════════════════════════════════════════
# TOPIC → SUBMIT
# ═══════════════════════════════════════════════════════════════
@app.route("/topics/<int:topic_id>/submit")
def topic_submit(topic_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    with db_cursor() as cur:
        # ← CHANGED: route through chapters
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
            return "Topic not found", 404

        user_has_access = has_access(user_id, topic["goal_id"])
        if topic["access_level"] == "paid" and not user_has_access:
            return redirect(f"/topics/{topic_id}/start")

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

        correct_count = counts["correct_count"] or 0
        wrong_count = counts["wrong_count"] or 0

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM questions
            WHERE topic_id = %s
              AND context IN ('practice', 'both')
        """, (topic_id,))
        total_questions = cur.fetchone()["total"]

    return render_template(
        "submit.html",
        topic=topic,
        correct_count=correct_count,
        wrong_count=wrong_count,
        total_questions=total_questions,
    )


# ═══════════════════════════════════════════════════════════════
# TOPIC → REVIEW
# ═══════════════════════════════════════════════════════════════
@app.route("/topics/<int:topic_id>/review")
def topic_review(topic_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    with db_cursor() as cur:
        # ← CHANGED: route through chapters
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
            return "Topic not found", 404

        user_has_access = has_access(user_id, topic["goal_id"])
        if topic["access_level"] == "paid" and not user_has_access:
            return redirect(f"/topics/{topic_id}/start")

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

    return render_template(
        "review.html",
        topic=topic,
        correct_count=counts["correct_count"] or 0,
        wrong_count=counts["wrong_count"] or 0,
        total_questions=total_questions,
    )


# ═══════════════════════════════════════════════════════════════
# TOPIC → REVIEW QUESTIONS
# ═══════════════════════════════════════════════════════════════
@app.route("/topics/<int:topic_id>/review/questions")
def topic_review_questions(topic_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    with db_cursor() as cur:
        # ← CHANGED: route through chapters
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
            return "Topic not found", 404

        user_has_access = has_access(user_id, topic["goal_id"])
        if topic["access_level"] == "paid" and not user_has_access:
            return redirect(f"/topics/{topic_id}/start")

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
              AND question_id IN (SELECT id FROM questions WHERE topic_id = %s)
        """, (user_id, topic_id))
        bookmarked_ids = [r["question_id"] for r in cur.fetchall()]

    questions = [
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
    ]

    return render_template(
        "review_questions.html",
        topic=topic,
        questions=questions,
        bookmarked_ids=bookmarked_ids,
    )

@app.route("/switch-goal")
def switch_goal_page():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    with db_cursor() as cur:
        # Get current goal
        cur.execute("SELECT current_goal_id FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        current_goal_id = user["current_goal_id"] if user else None

        # Get all goals
        cur.execute("SELECT id, name FROM goals ORDER BY name")
        goals = cur.fetchall()

    return render_template(
        "switch_goal.html",
        goals=goals,
        current_goal_id=current_goal_id
    )


@app.route("/switch-goal/select", methods=["POST"])
def switch_goal():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, message="Not logged in"), 401

    data = request.get_json() or {}
    goal_id = data.get("goal_id")

    if not goal_id:
        return jsonify(success=False, message="goal_id required"), 400

    with db_cursor() as cur:
        # Verify goal exists
        cur.execute("SELECT id FROM goals WHERE id = %s", (goal_id,))
        if not cur.fetchone():
            return jsonify(success=False, message="Goal not found"), 404

        # Update the user's goal
        cur.execute("""
            UPDATE users SET current_goal_id = %s WHERE id = %s
        """, (goal_id, user_id))

    return jsonify(success=True, redirect="/home")



if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)