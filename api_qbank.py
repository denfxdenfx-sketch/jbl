# api_qbank.py

from flask import Blueprint, jsonify, request, g
from db import db_cursor
from access import has_access
from api_auth import api_login_required


api_qbank_bp = Blueprint("api_qbank", __name__, url_prefix="/api/qbank")


# ═══════════════════════════════════════════════════════════════
# HELPERS (mirror of qbank.py, but JSON-shaped)
# ═══════════════════════════════════════════════════════════════

def _load_subject_topics(cur, subject_id, user_id, selected_cats):
    """
    Same shape as the HTML helper, but returns plain dicts suitable
    for jsonify. Adds a `locked` flag based on subscription access.
    """
    # Chapters for this subject
    cur.execute("""
        SELECT id, name
        FROM chapters
        WHERE subject_id = %s
        ORDER BY position, id
    """, (subject_id,))
    chapters = cur.fetchall()

    chapter_ids = [c["id"] for c in chapters]
    if not chapter_ids:
        return []

    # Topics
    cur.execute("""
        SELECT id, chapter_id, name, access_level, position
        FROM qbank_topics
        WHERE chapter_id = ANY(%s)
        ORDER BY chapter_id, position, id
    """, (chapter_ids,))
    topics = cur.fetchall()

    topic_ids = [t["id"] for t in topics]
    if not topic_ids:
        return []

    # Category rows per topic
    if selected_cats:
        cur.execute("""
            SELECT DISTINCT qbank_topic_id, category_id
            FROM qbank_questions
            WHERE qbank_topic_id = ANY(%s)
              AND category_id = ANY(%s)
        """, (topic_ids, selected_cats))
    else:
        cur.execute("""
            SELECT DISTINCT qbank_topic_id, category_id
            FROM qbank_questions
            WHERE qbank_topic_id = ANY(%s)
        """, (topic_ids,))
    topic_cat_rows = cur.fetchall()

    # Completion
    cur.execute("""
        SELECT qbank_topic_id, category_id
        FROM qbank_section_completion
        WHERE user_id = %s AND qbank_topic_id = ANY(%s)
    """, (user_id, topic_ids))
    completed_set = {(r["qbank_topic_id"], r["category_id"]) for r in cur.fetchall()}

    # Category meta
    cur.execute("""
        SELECT id, code, label, position
        FROM question_categories
        WHERE is_active = TRUE
        ORDER BY position
    """)
    cat_meta = {c["id"]: c for c in cur.fetchall()}

    # Group
    cats_by_topic = {}
    for row in topic_cat_rows:
        cats_by_topic.setdefault(row["qbank_topic_id"], []).append(row["category_id"])

    for tid in cats_by_topic:
        cats_by_topic[tid].sort(
            key=lambda cid: cat_meta[cid]["position"] if cid in cat_meta else 99
        )

    topics_by_chapter = {}
    for t in topics:
        topics_by_chapter.setdefault(t["chapter_id"], []).append(t)

    # Build payload
    chapter_payloads = []
    for c in chapters:
        c_topics = []
        for t in topics_by_chapter.get(c["id"], []):
            t_cats = []
            for cid in cats_by_topic.get(t["id"], []):
                t_cats.append({
                    "id": cid,
                    "label": cat_meta[cid]["label"] if cid in cat_meta else str(cid),
                    "completed": (t["id"], cid) in completed_set,
                })
            c_topics.append({
                "id": t["id"],
                "name": t["name"],
                "access_level": t["access_level"],
                "categories": t_cats,
            })
        chapter_payloads.append({
            "id": c["id"],
            "name": c["name"],
            "topics": c_topics,
        })

    return chapter_payloads


def _find_next_step(cur, user_id, current_topic_id, current_category_id, selected_cats):
    """
    Same as the HTML version. Returns {"topic_id", "category_id"} or None.
    """
    cur.execute("""
        SELECT s.id AS subject_id
        FROM qbank_topics qt
        JOIN chapters c ON qt.chapter_id = c.id
        JOIN subjects s ON c.subject_id = s.id
        WHERE qt.id = %s
    """, (current_topic_id,))
    row = cur.fetchone()
    if not row:
        return None
    subject_id = row["subject_id"]

    if selected_cats:
        cur.execute("""
            SELECT
                qt.id AS topic_id,
                q.category_id,
                c.position AS chapter_position,
                qt.position AS topic_position,
                qc.position AS category_position
            FROM qbank_topics qt
            JOIN chapters c ON qt.chapter_id = c.id
            JOIN (
                SELECT DISTINCT qbank_topic_id, category_id FROM qbank_questions
            ) q ON q.qbank_topic_id = qt.id
            JOIN question_categories qc ON q.category_id = qc.id
            WHERE c.subject_id = %s
              AND q.category_id = ANY(%s)
            ORDER BY c.position, qt.position, qc.position
        """, (subject_id, selected_cats))
    else:
        cur.execute("""
            SELECT
                qt.id AS topic_id,
                q.category_id,
                c.position AS chapter_position,
                qt.position AS topic_position,
                qc.position AS category_position
            FROM qbank_topics qt
            JOIN chapters c ON qt.chapter_id = c.id
            JOIN (
                SELECT DISTINCT qbank_topic_id, category_id FROM qbank_questions
            ) q ON q.qbank_topic_id = qt.id
            JOIN question_categories qc ON q.category_id = qc.id
            WHERE c.subject_id = %s
            ORDER BY c.position, qt.position, qc.position
        """, (subject_id,))
    steps = cur.fetchall()

    current_index = None
    for i, s in enumerate(steps):
        if s["topic_id"] == current_topic_id and s["category_id"] == current_category_id:
            current_index = i
            break
    if current_index is None:
        return None

    cur.execute("""
        SELECT qbank_topic_id, category_id
        FROM qbank_section_completion
        WHERE user_id = %s
    """, (user_id,))
    completed_set = {(r["qbank_topic_id"], r["category_id"]) for r in cur.fetchall()}

    for i in range(current_index + 1, len(steps)):
        s = steps[i]
        if (s["topic_id"], s["category_id"]) not in completed_set:
            return {"topic_id": s["topic_id"], "category_id": s["category_id"]}

    return None


def _parse_cats_param():
    """Read ?cats=1,2,3 from the request and return a list of ints, or None."""
    cats_param = request.args.get("cats")
    if not cats_param:
        return None
    try:
        return [int(x) for x in cats_param.split(",") if x.strip()]
    except ValueError:
        return []


# ═══════════════════════════════════════════════════════════════
# HOME
# ═══════════════════════════════════════════════════════════════
@api_qbank_bp.route("/home")
@api_login_required
def api_qbank_home():
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT u.first_name, u.current_goal_id, g.name AS goal_name
            FROM users u
            LEFT JOIN goals g ON u.current_goal_id = g.id
            WHERE u.id = %s
        """, (user_id,))
        user = cur.fetchone()

        if not user or not user["current_goal_id"]:
            return jsonify(
                success=True,
                first_name=(user or {}).get("first_name") or "there",
                goal_name=None,
                subjects=[],
            )

        goal_id = user["current_goal_id"]

        cur.execute("""
            SELECT
                s.id                AS subject_id,
                s.name              AS subject_name,
                COUNT(qt.id)        AS total_topics,
                COUNT(c.id)         AS completed_topics
            FROM subjects s
            LEFT JOIN chapters ch
                ON ch.subject_id = s.id
            LEFT JOIN qbank_topics qt
                ON qt.chapter_id = ch.id
            LEFT JOIN qbank_topic_completion c
                ON c.qbank_topic_id = qt.id AND c.user_id = %s
            WHERE s.goal_id = %s
            GROUP BY s.id, s.name
            ORDER BY s.id
        """, (user_id, goal_id))
        subjects = cur.fetchall()

    return jsonify(
        success=True,
        first_name=user["first_name"] or "there",
        goal_name=user["goal_name"],
        subjects=[
            {
                "subject_id": s["subject_id"],
                "subject_name": s["subject_name"],
                "total_topics": s["total_topics"],
                "completed_topics": s["completed_topics"],
            }
            for s in subjects
        ],
    )


# ═══════════════════════════════════════════════════════════════
# SUBJECT → CHAPTERS → TOPICS → CATEGORIES
# ═══════════════════════════════════════════════════════════════
@api_qbank_bp.route("/subjects/<int:subject_id>/topics")
@api_login_required
def api_qbank_subject_topics(subject_id):
    user_id = g.user_id
    selected_cats = _parse_cats_param()

    with db_cursor() as cur:
        # Subject
        cur.execute("""
            SELECT s.id, s.name, s.goal_id, g.name AS goal_name
            FROM subjects s
            JOIN goals g ON s.goal_id = g.id
            WHERE s.id = %s
        """, (subject_id,))
        subject = cur.fetchone()
        if not subject:
            return jsonify(success=False, message="Subject not found"), 404

        # All active categories
        cur.execute("""
            SELECT id, code, label, position
            FROM question_categories
            WHERE is_active = TRUE
            ORDER BY position
        """)
        all_categories = cur.fetchall()

        if selected_cats is None:
            selected_cats = [c["id"] for c in all_categories]

        chapters = _load_subject_topics(cur, subject_id, user_id, selected_cats)

    user_has_access = has_access(user_id, subject["goal_id"])

    # Annotate lock
    for ch in chapters:
        for t in ch["topics"]:
            t["locked"] = (t["access_level"] == "paid") and not user_has_access

    return jsonify(
        success=True,
        subject={
            "id": subject["id"],
            "name": subject["name"],
            "goal_id": subject["goal_id"],
            "goal_name": subject["goal_name"],
        },
        chapters=chapters,
        all_categories=[
            {"id": c["id"], "code": c["code"], "label": c["label"], "position": c["position"]}
            for c in all_categories
        ],
        selected_cats=selected_cats,
    )


# ═══════════════════════════════════════════════════════════════
# TOPIC + CATEGORY → QUESTIONS
# ═══════════════════════════════════════════════════════════════
@api_qbank_bp.route("/topics/<int:topic_id>/categories/<int:category_id>/questions")
@api_login_required
def api_qbank_category_questions(topic_id, category_id):
    user_id = g.user_id
    selected_cats = _parse_cats_param()

    with db_cursor() as cur:
        # Topic
        cur.execute("""
            SELECT qt.id, qt.name, qt.access_level,
                   s.id AS subject_id,
                   s.goal_id, g.name AS goal_name
            FROM qbank_topics qt
            JOIN chapters c ON qt.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            JOIN goals g ON s.goal_id = g.id
            WHERE qt.id = %s
        """, (topic_id,))
        topic = cur.fetchone()
        if not topic:
            return jsonify(success=False, message="QBank topic not found"), 404

        user_has_access = has_access(user_id, topic["goal_id"])
        if topic["access_level"] == "paid" and not user_has_access:
            return jsonify(success=False, message="Subscription required"), 403

        # Category
        cur.execute("""
            SELECT id, code, label, position
            FROM question_categories
            WHERE id = %s
        """, (category_id,))
        category = cur.fetchone()
        if not category:
            return jsonify(success=False, message="Category not found"), 404

        # Already completed?
        cur.execute("""
            SELECT 1 FROM qbank_section_completion
            WHERE user_id = %s AND qbank_topic_id = %s AND category_id = %s
        """, (user_id, topic_id, category_id))
        if cur.fetchone():
            return jsonify(
                success=True,
                already_complete=True,
                review_url=f"/qbank/topics/{topic_id}/categories/{category_id}/review",
            )

        # Questions
        cur.execute("""
            SELECT id, text, answer, image_path, answer_image_path, position
            FROM qbank_questions
            WHERE qbank_topic_id = %s AND category_id = %s
            ORDER BY position, id
        """, (topic_id, category_id))
        questions = cur.fetchall()

        qids = [q["id"] for q in questions]

        # Notes
        notes = {}
        if qids:
            cur.execute("""
                SELECT qbank_question_id, notes
                FROM user_qbank_notes
                WHERE user_id = %s AND qbank_question_id = ANY(%s)
            """, (user_id, qids))
            notes = {r["qbank_question_id"]: r["notes"] for r in cur.fetchall()}

        # Bookmarks
        bookmarks = set()
        if qids:
            cur.execute("""
                SELECT qbank_question_id
                FROM user_qbank_bookmarks
                WHERE user_id = %s AND qbank_question_id = ANY(%s)
            """, (user_id, qids))
            bookmarks = {r["qbank_question_id"] for r in cur.fetchall()}

        # All categories
        cur.execute("""
            SELECT id, code, label, position
            FROM question_categories
            WHERE is_active = TRUE
            ORDER BY position
        """)
        all_categories = cur.fetchall()

    if selected_cats is None:
        selected_cats = [c["id"] for c in all_categories]

    return jsonify(
        success=True,
        already_complete=False,
        topic={
            "id": topic["id"],
            "name": topic["name"],
            "access_level": topic["access_level"],
            "subject_id": topic["subject_id"],
            "goal_id": topic["goal_id"],
        },
        category={
            "id": category["id"],
            "code": category["code"],
            "label": category["label"],
        },
        questions=[
            {
                "id": q["id"],
                "text": q["text"],
                "answer": q["answer"],
                "image_path": q["image_path"],
                "answer_image_path": q["answer_image_path"],
                "position": q["position"],
            }
            for q in questions
        ],
        notes=notes,
        bookmarks=list(bookmarks),
        all_categories=[
            {"id": c["id"], "code": c["code"], "label": c["label"], "position": c["position"]}
            for c in all_categories
        ],
        selected_cats=selected_cats,
    )


# ═══════════════════════════════════════════════════════════════
# TOPIC + CATEGORY → REVIEW
# ═══════════════════════════════════════════════════════════════
@api_qbank_bp.route("/topics/<int:topic_id>/categories/<int:category_id>/review")
@api_login_required
def api_qbank_category_review(topic_id, category_id):
    user_id = g.user_id
    selected_cats = _parse_cats_param()

    with db_cursor() as cur:
        # Topic
        cur.execute("""
            SELECT qt.id, qt.name, qt.access_level,
                   s.id AS subject_id,
                   s.goal_id, g.name AS goal_name
            FROM qbank_topics qt
            JOIN chapters c ON qt.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            JOIN goals g ON s.goal_id = g.id
            WHERE qt.id = %s
        """, (topic_id,))
        topic = cur.fetchone()
        if not topic:
            return jsonify(success=False, message="QBank topic not found"), 404

        user_has_access = has_access(user_id, topic["goal_id"])
        if topic["access_level"] == "paid" and not user_has_access:
            return jsonify(success=False, message="Subscription required"), 403

        # Category
        cur.execute("""
            SELECT id, code, label, position
            FROM question_categories
            WHERE id = %s
        """, (category_id,))
        category = cur.fetchone()
        if not category:
            return jsonify(success=False, message="Category not found"), 404

        # Questions
        cur.execute("""
            SELECT id, text, answer, image_path, answer_image_path, position
            FROM qbank_questions
            WHERE qbank_topic_id = %s AND category_id = %s
            ORDER BY position, id
        """, (topic_id, category_id))
        questions = cur.fetchall()

        qids = [q["id"] for q in questions]

        notes = {}
        if qids:
            cur.execute("""
                SELECT qbank_question_id, notes
                FROM user_qbank_notes
                WHERE user_id = %s AND qbank_question_id = ANY(%s)
            """, (user_id, qids))
            notes = {r["qbank_question_id"]: r["notes"] for r in cur.fetchall()}

        bookmarks = set()
        if qids:
            cur.execute("""
                SELECT qbank_question_id
                FROM user_qbank_bookmarks
                WHERE user_id = %s AND qbank_question_id = ANY(%s)
            """, (user_id, qids))
            bookmarks = {r["qbank_question_id"] for r in cur.fetchall()}

        cur.execute("""
            SELECT id, code, label, position
            FROM question_categories
            WHERE is_active = TRUE
            ORDER BY position
        """)
        all_categories = cur.fetchall()

    if selected_cats is None:
        selected_cats = [c["id"] for c in all_categories]

    return jsonify(
        success=True,
        review_mode=True,
        topic={
            "id": topic["id"],
            "name": topic["name"],
            "access_level": topic["access_level"],
            "subject_id": topic["subject_id"],
            "goal_id": topic["goal_id"],
        },
        category={
            "id": category["id"],
            "code": category["code"],
            "label": category["label"],
        },
        questions=[
            {
                "id": q["id"],
                "text": q["text"],
                "answer": q["answer"],
                "image_path": q["image_path"],
                "answer_image_path": q["answer_image_path"],
                "position": q["position"],
            }
            for q in questions
        ],
        notes=notes,
        bookmarks=list(bookmarks),
        all_categories=[
            {"id": c["id"], "code": c["code"], "label": c["label"], "position": c["position"]}
            for c in all_categories
        ],
        selected_cats=selected_cats,
    )


# ═══════════════════════════════════════════════════════════════
# MARK CATEGORY COMPLETE
# ═══════════════════════════════════════════════════════════════
@api_qbank_bp.route("/topics/<int:topic_id>/categories/<int:category_id>/complete", methods=["POST"])
@api_login_required
def api_qbank_category_complete(topic_id, category_id):
    user_id = g.user_id

    # Filter can come from JSON body or from ?cats=
    data = request.get_json() or {}
    selected_cats = data.get("cats")
    if selected_cats is None:
        selected_cats = _parse_cats_param()

    with db_cursor() as cur:
        # Verify topic
        cur.execute("SELECT id FROM qbank_topics WHERE id = %s", (topic_id,))
        if not cur.fetchone():
            return jsonify(success=False, message="Topic not found"), 404

        # Verify category
        cur.execute("SELECT id FROM question_categories WHERE id = %s", (category_id,))
        if not cur.fetchone():
            return jsonify(success=False, message="Category not found"), 400

        # Mark complete (idempotent)
        cur.execute("""
            INSERT INTO qbank_section_completion
                (user_id, qbank_topic_id, category_id, completed_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (user_id, qbank_topic_id, category_id) DO NOTHING
        """, (user_id, topic_id, category_id))

        # If all categories in the topic are done, mark topic complete
        cur.execute("""
            SELECT DISTINCT category_id FROM qbank_questions
            WHERE qbank_topic_id = %s
        """, (topic_id,))
        needed = {row["category_id"] for row in cur.fetchall()}

        cur.execute("""
            SELECT category_id FROM qbank_section_completion
            WHERE user_id = %s AND qbank_topic_id = %s
        """, (user_id, topic_id))
        done = {row["category_id"] for row in cur.fetchall()}

        if needed and needed.issubset(done):
            cur.execute("""
                INSERT INTO qbank_topic_completion
                    (user_id, qbank_topic_id, completed_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (user_id, qbank_topic_id) DO NOTHING
            """, (user_id, topic_id))

        next_step = _find_next_step(cur, user_id, topic_id, category_id, selected_cats)

    return jsonify(
        success=True,
        section_complete=True,
        next_step=next_step,   # {"topic_id", "category_id"} or None
    )


# ═══════════════════════════════════════════════════════════════
# SAVE NOTE
# ═══════════════════════════════════════════════════════════════
@api_qbank_bp.route("/questions/<int:question_id>/note", methods=["POST"])
@api_login_required
def api_qbank_save_note(question_id):
    user_id = g.user_id
    data = request.get_json() or {}
    text = data.get("notes", "")

    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO user_qbank_notes (user_id, qbank_question_id, notes, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (user_id, qbank_question_id)
            DO UPDATE SET notes = EXCLUDED.notes, updated_at = NOW()
        """, (user_id, question_id, text))

    return jsonify(success=True)


# ═══════════════════════════════════════════════════════════════
# TOGGLE BOOKMARK
# ═══════════════════════════════════════════════════════════════
@api_qbank_bp.route("/questions/<int:question_id>/bookmark", methods=["POST"])
@api_login_required
def api_qbank_toggle_bookmark(question_id):
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT 1 FROM user_qbank_bookmarks
            WHERE user_id = %s AND qbank_question_id = %s
        """, (user_id, question_id))
        exists = cur.fetchone() is not None

        if exists:
            cur.execute("""
                DELETE FROM user_qbank_bookmarks
                WHERE user_id = %s AND qbank_question_id = %s
            """, (user_id, question_id))
            bookmarked = False
        else:
            cur.execute("""
                INSERT INTO user_qbank_bookmarks (user_id, qbank_question_id)
                VALUES (%s, %s)
            """, (user_id, question_id))
            bookmarked = True

    return jsonify(success=True, bookmarked=bookmarked)


# ═══════════════════════════════════════════════════════════════
# BOOKMARKS — subjects list
# ═══════════════════════════════════════════════════════════════
@api_qbank_bp.route("/bookmarks")
@api_login_required
def api_qbank_bookmarks_home():
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT
                s.id AS subject_id,
                s.name AS subject_name,
                g.name AS goal_name,
                COUNT(ub.id) AS bookmark_count
            FROM user_qbank_bookmarks ub
            JOIN qbank_questions q ON ub.qbank_question_id = q.id
            JOIN qbank_topics qt ON q.qbank_topic_id = qt.id
            JOIN chapters c ON qt.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            JOIN goals g ON s.goal_id = g.id
            WHERE ub.user_id = %s
            GROUP BY s.id, s.name, g.name
            ORDER BY g.name, s.name
        """, (user_id,))
        subjects = cur.fetchall()

    return jsonify(
        success=True,
        subjects=[
            {
                "subject_id": s["subject_id"],
                "subject_name": s["subject_name"],
                "goal_name": s["goal_name"],
                "bookmark_count": s["bookmark_count"],
            }
            for s in subjects
        ],
    )


# ═══════════════════════════════════════════════════════════════
# BOOKMARKS — questions within a subject
# ═══════════════════════════════════════════════════════════════
@api_qbank_bp.route("/bookmarks/subject/<int:subject_id>")
@api_login_required
def api_qbank_bookmarks_for_subject(subject_id):
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("SELECT id, name FROM subjects WHERE id = %s", (subject_id,))
        subject = cur.fetchone()
        if not subject:
            return jsonify(success=False, message="Subject not found"), 404

        cur.execute("""
            SELECT
                q.id AS question_id,
                q.text,
                q.answer,
                q.image_path,
                q.answer_image_path,
                q.category_id,
                qc.label AS category_label,
                qt.name AS topic_name,
                ub.created_at AS bookmarked_at
            FROM user_qbank_bookmarks ub
            JOIN qbank_questions q ON ub.qbank_question_id = q.id
            JOIN qbank_topics qt ON q.qbank_topic_id = qt.id
            JOIN chapters c ON qt.chapter_id = c.id
            JOIN question_categories qc ON q.category_id = qc.id
            WHERE ub.user_id = %s AND c.subject_id = %s
            ORDER BY ub.created_at DESC
        """, (user_id, subject_id))
        rows = cur.fetchall()

    return jsonify(
        success=True,
        subject={"id": subject["id"], "name": subject["name"]},
        questions=[
            {
                "id": r["question_id"],
                "text": r["text"],
                "answer": r["answer"],
                "image_path": r["image_path"],
                "answer_image_path": r["answer_image_path"],
                "category_id": r["category_id"],
                "category_label": r["category_label"],
                "topic_name": r["topic_name"],
                "bookmarked_at": r["bookmarked_at"].isoformat() if r["bookmarked_at"] else None,
            }
            for r in rows
        ],
    )

# ═══════════════════════════════════════════════════════════════
# API: QBank Years — list all year papers for the user's goal
# ═══════════════════════════════════════════════════════════════
@api_qbank_bp.route("/years", methods=["GET"])
@api_login_required
def api_qbank_years():
    user_id = g.user_id

    # Optional ?subject=<id>
    subject_filter_raw = request.args.get("subject")
    try:
        subject_filter = int(subject_filter_raw) if subject_filter_raw else None
    except (TypeError, ValueError):
        subject_filter = None

    with db_cursor() as cur:
        cur.execute("""
            SELECT u.current_goal_id, g.name AS goal_name
            FROM users u
            LEFT JOIN goals g ON u.current_goal_id = g.id
            WHERE u.id = %s
        """, (user_id,))
        user = cur.fetchone()

        if not user or not user["current_goal_id"]:
            return jsonify(
                success=False,
                message="No goal selected. Please choose a goal first.",
                needs_goal=True,
            ), 400

        goal_id = user["current_goal_id"]
        goal_name = user["goal_name"]

        # Subject list for filter dropdown
        cur.execute("""
            SELECT id, name FROM subjects
            WHERE goal_id = %s
            ORDER BY id
        """, (goal_id,))
        all_subjects = cur.fetchall()

        # (subject, year, type) rows
        base_query = """
            SELECT
                s.id AS subject_id,
                s.name AS subject_name,
                q.exam_year,
                q.exam_type,
                COUNT(q.id) AS total
            FROM qbank_questions q
            JOIN qbank_topics qt ON q.qbank_topic_id = qt.id
            JOIN chapters c ON qt.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            WHERE s.goal_id = %s
              AND q.exam_year IS NOT NULL
              AND q.exam_type IS NOT NULL
        """

        if subject_filter:
            cur.execute(
                base_query + """
                  AND s.id = %s
                GROUP BY s.id, s.name, q.exam_year, q.exam_type
                ORDER BY s.id,
                         q.exam_year DESC,
                         CASE q.exam_type
                             WHEN 'regular' THEN 1
                             WHEN 'supplementary' THEN 2
                             ELSE 3 END
                """,
                (goal_id, subject_filter),
            )
        else:
            cur.execute(
                base_query + """
                GROUP BY s.id, s.name, q.exam_year, q.exam_type
                ORDER BY s.id,
                         q.exam_year DESC,
                         CASE q.exam_type
                             WHEN 'regular' THEN 1
                             WHEN 'supplementary' THEN 2
                             ELSE 3 END
                """,
                (goal_id,),
            )
        rows = cur.fetchall()

        # Completed papers
        cur.execute("""
            SELECT subject_id, exam_year, exam_type
            FROM qbank_year_paper_completion
            WHERE user_id = %s AND goal_id = %s
        """, (user_id, goal_id))
        completed = {
            (r["subject_id"], r["exam_year"], r["exam_type"])
            for r in cur.fetchall()
        }

    # Group by subject
    subjects_map = {}
    for r in rows:
        sid = r["subject_id"]
        if sid not in subjects_map:
            subjects_map[sid] = {
                "subject_id": sid,
                "subject_name": r["subject_name"],
                "papers": [],
            }
        subjects_map[sid]["papers"].append({
            "year": r["exam_year"],
            "type": r["exam_type"],
            "total": r["total"],
            "completed": (sid, r["exam_year"], r["exam_type"]) in completed,
        })

    selected_subject = None
    if subject_filter:
        for s in all_subjects:
            if s["id"] == subject_filter:
                selected_subject = {"id": s["id"], "name": s["name"]}
                break

    return jsonify(
        success=True,
        goal={"id": goal_id, "name": goal_name},
        subjects=list(subjects_map.values()),
        all_subjects=[{"id": s["id"], "name": s["name"]} for s in all_subjects],
        selected_subject=selected_subject,
    )


# ═══════════════════════════════════════════════════════════════
# API: Year → Subject → Topics
# ═══════════════════════════════════════════════════════════════
@api_qbank_bp.route(
    "/years/<int:year>/<exam_type>/subjects/<int:subject_id>/topics",
    methods=["GET"],
)
@api_login_required
def api_qbank_year_subject_topics(year, exam_type, subject_id):
    user_id = g.user_id

    if exam_type not in ("regular", "supplementary"):
        return jsonify(success=False, message="Invalid paper type"), 400

    with db_cursor() as cur:
        cur.execute("SELECT current_goal_id FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user or not user["current_goal_id"]:
            return jsonify(success=False, message="No goal selected"), 400
        goal_id = user["current_goal_id"]

        # Subject metadata
        cur.execute("""
            SELECT s.id, s.name, s.goal_id, g.name AS goal_name
            FROM subjects s
            JOIN goals g ON s.goal_id = g.id
            WHERE s.id = %s
        """, (subject_id,))
        subject = cur.fetchone()
        if not subject:
            return jsonify(success=False, message="Subject not found"), 404

        # Topics in this subject for this paper
        cur.execute("""
            SELECT DISTINCT
                c.id AS chapter_id,
                c.name AS chapter_name,
                c.position AS chapter_position,
                qt.id AS topic_id,
                qt.name AS topic_name,
                qt.access_level,
                qt.position AS topic_position
            FROM qbank_questions q
            JOIN qbank_topics qt ON q.qbank_topic_id = qt.id
            JOIN chapters c ON qt.chapter_id = c.id
            WHERE c.subject_id = %s
              AND q.exam_year = %s
              AND q.exam_type = %s
            ORDER BY c.position, qt.position
        """, (subject_id, year, exam_type))
        topic_rows = cur.fetchall()

        if not topic_rows:
            return jsonify(
                success=True,
                message="No topics for this paper yet",
                chapters=[],
            )

        # Categories per topic + completion
        cur.execute("""
            SELECT DISTINCT
                q.qbank_topic_id AS topic_id,
                q.category_id,
                qc.label,
                qc.position,
                EXISTS (
                    SELECT 1 FROM qbank_topic_year_completion tyc
                    WHERE tyc.user_id = %s
                      AND tyc.goal_id = %s
                      AND tyc.subject_id = %s
                      AND tyc.qbank_topic_id = q.qbank_topic_id
                      AND tyc.category_id = q.category_id
                      AND tyc.exam_year = %s
                      AND tyc.exam_type = %s
                ) AS completed
            FROM qbank_questions q
            JOIN question_categories qc ON q.category_id = qc.id
            WHERE q.exam_year = %s
              AND q.exam_type = %s
              AND q.qbank_topic_id = ANY(%s)
            ORDER BY qc.position
        """, (
            user_id, goal_id, subject_id, year, exam_type,
            year, exam_type,
            [r["topic_id"] for r in topic_rows],
        ))
        cat_rows = cur.fetchall()

        cats_by_topic = {}
        for c in cat_rows:
            cats_by_topic.setdefault(c["topic_id"], []).append({
                "id": c["category_id"],
                "label": c["label"],
                "completed": c["completed"],
            })

        # Group topics under chapters
        chapters_map = {}
        for r in topic_rows:
            ch_id = r["chapter_id"]
            if ch_id not in chapters_map:
                chapters_map[ch_id] = {
                    "id": ch_id,
                    "name": r["chapter_name"],
                    "position": r["chapter_position"],
                    "topics": [],
                }
            chapters_map[ch_id]["topics"].append({
                "id": r["topic_id"],
                "name": r["topic_name"],
                "access_level": r["access_level"],
                "categories": cats_by_topic.get(r["topic_id"], []),
            })

        chapters = [
            chapters_map[k]
            for k in sorted(chapters_map.keys(),
                            key=lambda k: chapters_map[k]["position"])
        ]

        # Is this paper done for this subject?
        cur.execute("""
            SELECT 1 FROM qbank_year_paper_completion
            WHERE user_id = %s AND goal_id = %s AND subject_id = %s
              AND exam_year = %s AND exam_type = %s
        """, (user_id, goal_id, subject_id, year, exam_type))
        is_completed = cur.fetchone() is not None

    return jsonify(
        success=True,
        year=year,
        exam_type=exam_type,
        subject={
            "id": subject["id"],
            "name": subject["name"],
            "goal_id": subject["goal_id"],
            "goal_name": subject["goal_name"],
        },
        is_completed=is_completed,
        chapters=chapters,
    )


# ═══════════════════════════════════════════════════════════════
# API: Year → Subject → Topic + Category → Questions
# ═══════════════════════════════════════════════════════════════
@api_qbank_bp.route(
    "/years/<int:year>/<exam_type>/topics/<int:topic_id>/categories/<int:category_id>",
    methods=["GET"],
)
@api_login_required
def api_qbank_year_category_questions(year, exam_type, topic_id, category_id):
    user_id = g.user_id

    if exam_type not in ("regular", "supplementary"):
        return jsonify(success=False, message="Invalid paper type"), 400

    with db_cursor() as cur:
        cur.execute("SELECT current_goal_id FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user or not user["current_goal_id"]:
            return jsonify(success=False, message="No goal selected"), 400
        goal_id = user["current_goal_id"]

        # Topic
        cur.execute("""
            SELECT qt.id, qt.name, qt.access_level,
                   s.id AS subject_id, s.name AS subject_name,
                   s.goal_id, g.name AS goal_name
            FROM qbank_topics qt
            JOIN chapters c ON qt.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            JOIN goals g ON s.goal_id = g.id
            WHERE qt.id = %s
        """, (topic_id,))
        topic = cur.fetchone()
        if not topic:
            return jsonify(success=False, message="Topic not found"), 404

        # Category
        cur.execute("""
            SELECT id, code, label, position
            FROM question_categories
            WHERE id = %s
        """, (category_id,))
        category = cur.fetchone()
        if not category:
            return jsonify(success=False, message="Category not found"), 404

        # Already completed?
        cur.execute("""
            SELECT 1 FROM qbank_topic_year_completion
            WHERE user_id = %s AND goal_id = %s AND subject_id = %s
              AND qbank_topic_id = %s
              AND category_id = %s AND exam_year = %s AND exam_type = %s
        """, (user_id, goal_id, topic["subject_id"], topic_id,
              category_id, year, exam_type))
        already_done = cur.fetchone() is not None

        # Questions
        cur.execute("""
            SELECT id, text, answer, image_path, answer_image_path, position
            FROM qbank_questions
            WHERE qbank_topic_id = %s
              AND category_id = %s
              AND exam_year = %s
              AND exam_type = %s
            ORDER BY position, id
        """, (topic_id, category_id, year, exam_type))
        questions = cur.fetchall()

        if not questions:
            return jsonify(
                success=True,
                message="No questions in this section",
                questions=[],
            )

        qids = [q["id"] for q in questions]

        # Notes
        cur.execute("""
            SELECT qbank_question_id, notes
            FROM user_qbank_notes
            WHERE user_id = %s AND qbank_question_id = ANY(%s)
        """, (user_id, qids))
        notes = {r["qbank_question_id"]: r["notes"] for r in cur.fetchall()}

        # Bookmarks
        cur.execute("""
            SELECT qbank_question_id
            FROM user_qbank_bookmarks
            WHERE user_id = %s AND qbank_question_id = ANY(%s)
        """, (user_id, qids))
        bookmarks = {r["qbank_question_id"] for r in cur.fetchall()}

    return jsonify(
        success=True,
        year=year,
        exam_type=exam_type,
        review_mode=already_done,
        topic={
            "id": topic["id"],
            "name": topic["name"],
            "access_level": topic["access_level"],
            "subject_id": topic["subject_id"],
            "subject_name": topic["subject_name"],
            "goal_name": topic["goal_name"],
        },
        category={
            "id": category["id"],
            "code": category["code"],
            "label": category["label"],
        },
        questions=[
            {
                "id": q["id"],
                "text": q["text"],
                "answer": q["answer"],
                "image_path": q["image_path"],
                "answer_image_path": q["answer_image_path"],
                "position": q["position"],
                "notes": notes.get(q["id"], ""),
                "bookmarked": q["id"] in bookmarks,
            }
            for q in questions
        ],
    )


# ═══════════════════════════════════════════════════════════════
# YEAR-WISE: Complete a section (uses existing helpers)
# ═══════════════════════════════════════════════════════════════
@api_qbank_bp.route("/years/complete", methods=["POST"])
@api_login_required
def api_year_complete_section():
    # Import the helpers you already wrote
    from qbank_year_helpers import cascade_year_completion, find_next_step_in_paper 
    user_id = g.user_id
    data = request.get_json() or {}

    topic_id = data.get("topic_id")
    category_id = data.get("category_id")
    year = data.get("year")
    exam_type = data.get("exam_type")
    subject_id = data.get("subject_id")

    if not all([topic_id, category_id, year, exam_type, subject_id]):
        return jsonify(success=False, message="Missing fields"), 400

    if exam_type not in ("regular", "supplementary"):
        return jsonify(success=False, message="Invalid paper type"), 400

    with db_cursor() as cur:
        # Verify topic belongs to this subject
        cur.execute("""
            SELECT qt.id
            FROM qbank_topics qt
            JOIN chapters c ON qt.chapter_id = c.id
            WHERE qt.id = %s AND c.subject_id = %s
        """, (topic_id, subject_id))
        if not cur.fetchone():
            return jsonify(success=False, message="Topic / subject mismatch"), 404

        # Get user's goal
        cur.execute("SELECT current_goal_id FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user or not user["current_goal_id"]:
            return jsonify(success=False, message="No goal selected"), 400
        goal_id = user["current_goal_id"]

        # Mark complete + cascade paper completion
        paper_complete = cascade_year_completion(
            cur=cur,
            user_id=user_id,
            goal_id=goal_id,
            subject_id=subject_id,
            topic_id=topic_id,
            category_id=category_id,
            exam_year=year,
            exam_type=exam_type,
        )

        # Find the next uncompleted section in this paper
        next_step = find_next_step_in_paper(
            cur=cur,
            user_id=user_id,
            goal_id=goal_id,
            year=year,
            exam_type=exam_type,
            current_topic_id=topic_id,
            current_category_id=category_id,
        )

    return jsonify(
        success=True,
        paper_complete=paper_complete,
        next_step=next_step,   # {"topic_id", "category_id"} or None
    )