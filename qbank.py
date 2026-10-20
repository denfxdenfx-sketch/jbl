# qbank.py

from flask import Blueprint, render_template, session, request, jsonify, redirect
from db import db_cursor
from access import has_access, qbank_topic_is_completed

qbank_bp = Blueprint("qbank", __name__, url_prefix="/qbank")


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _load_subject_topics(cur, subject_id, user_id, selected_cats):
    """
    Load all topics for a subject with their categories.
    selected_cats: list of category ids to include, or None for all.
    Returns list of chapter payloads, each with topics, each with categories.
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

    # Topics for those chapters
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

    # Category rows for each topic (filtered)
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

    # Completion status for this user
    cur.execute("""
        SELECT qbank_topic_id, category_id
        FROM qbank_section_completion
        WHERE user_id = %s AND qbank_topic_id = ANY(%s)
    """, (user_id, topic_ids))
    completed_set = {(r["qbank_topic_id"], r["category_id"]) for r in cur.fetchall()}

    # Category metadata (labels, position)
    cur.execute("""
        SELECT id, code, label, position
        FROM question_categories
        WHERE is_active = TRUE
        ORDER BY position
    """)
    categories = cur.fetchall()
    cat_meta = {c["id"]: c for c in categories}

    # Group categories by topic
    cats_by_topic = {}
    for row in topic_cat_rows:
        cats_by_topic.setdefault(row["qbank_topic_id"], []).append(row["category_id"])

    # Sort each topic's categories by category position
    for tid in cats_by_topic:
        cats_by_topic[tid].sort(
            key=lambda cid: cat_meta[cid]["position"] if cid in cat_meta else 99
        )

    # Group topics by chapter
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
    Find the next (topic_id, category_id) in the subject's depth-first order,
    skipping any (topic, category) already completed by this user.
    Returns {"topic_id": x, "category_id": y} or None.
    """
    # Subject of the current topic
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

    # All (topic, category) pairs in this subject, ordered
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

    # Find current index
    current_index = None
    for i, s in enumerate(steps):
        if s["topic_id"] == current_topic_id and s["category_id"] == current_category_id:
            current_index = i
            break
    if current_index is None:
        return None

    # Completed pairs
    cur.execute("""
        SELECT qbank_topic_id, category_id
        FROM qbank_section_completion
        WHERE user_id = %s
    """, (user_id,))
    completed_set = {(r["qbank_topic_id"], r["category_id"]) for r in cur.fetchall()}

    # Find next uncompleted step
    for i in range(current_index + 1, len(steps)):
        s = steps[i]
        if (s["topic_id"], s["category_id"]) not in completed_set:
            return {"topic_id": s["topic_id"], "category_id": s["category_id"]}

    return None


# ═══════════════════════════════════════════════════════════════
# QBANK HOME
# ═══════════════════════════════════════════════════════════════
@qbank_bp.route("/home")
def qbank_home():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    with db_cursor() as cur:
        cur.execute("""
            SELECT u.first_name, u.current_goal_id, g.name AS goal_name
            FROM users u
            LEFT JOIN goals g ON u.current_goal_id = g.id
            WHERE u.id = %s
        """, (user_id,))
        user = cur.fetchone()

        if not user or not user["current_goal_id"]:
            return render_template(
                "qbank_home.html",
                first_name=(user or {}).get("first_name", "there"),
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

    return render_template(
        "qbank_home.html",
        first_name=user["first_name"] or "there",
        goal_name=user["goal_name"],
        subjects=subjects,
    )


# ═══════════════════════════════════════════════════════════════
# SUBJECT → CHAPTERS → TOPICS → CATEGORIES (chapter page)
# ═══════════════════════════════════════════════════════════════
@qbank_bp.route("/subjects/<int:subject_id>/topics")
def qbank_subject_topics(subject_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    # ── Read filter from URL ────────────────────────────
    cats_param = request.args.get("cats")
    if cats_param:
        try:
            selected_cats = [int(x) for x in cats_param.split(",") if x.strip()]
        except ValueError:
            selected_cats = []
    else:
        selected_cats = None

    with db_cursor() as cur:
        # Load subject
        cur.execute("""
            SELECT s.id, s.name, s.goal_id, g.name AS goal_name
            FROM subjects s
            JOIN goals g ON s.goal_id = g.id
            WHERE s.id = %s
        """, (subject_id,))
        subject = cur.fetchone()
        if not subject:
            return "Subject not found", 404

        # All active categories (for the filter chips)
        cur.execute("""
            SELECT id, code, label, position
            FROM question_categories
            WHERE is_active = TRUE
            ORDER BY position
        """)
        all_categories = cur.fetchall()

        # Default = all categories
        if selected_cats is None:
            selected_cats = [c["id"] for c in all_categories]

        # Build the payload
        chapters = _load_subject_topics(cur, subject_id, user_id, selected_cats)

    user_has_access = has_access(user_id, subject["goal_id"])

    # Annotate lock state
    for ch in chapters:
        for t in ch["topics"]:
            t["locked"] = (t["access_level"] == "paid") and not user_has_access

    return render_template(
        "qbank_topics.html",
        subject=subject,
        chapters=chapters,
        all_categories=all_categories,
        selected_cats=selected_cats,
    )


# ═══════════════════════════════════════════════════════════════
# TOPIC + CATEGORY → QUESTIONS
# ═══════════════════════════════════════════════════════════════
@qbank_bp.route("/topics/<int:topic_id>/categories/<int:category_id>/questions")
def qbank_category_questions(topic_id, category_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    # Read filter from URL to preserve it
    cats_param = request.args.get("cats")
    if cats_param:
        try:
            selected_cats = [int(x) for x in cats_param.split(",") if x.strip()]
        except ValueError:
            selected_cats = []
    else:
        selected_cats = None

    with db_cursor() as cur:
        # Load topic
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
            return "QBank topic not found", 404

        user_has_access = has_access(user_id, topic["goal_id"])
        if topic["access_level"] == "paid" and not user_has_access:
            return redirect(f"/qbank/subjects/{topic['subject_id']}/topics")

        # Load category
        cur.execute("""
            SELECT id, code, label, position
            FROM question_categories
            WHERE id = %s
        """, (category_id,))
        category = cur.fetchone()
        if not category:
            return "Category not found", 404

        # If already completed, go to review
        cur.execute("""
            SELECT 1 FROM qbank_section_completion
            WHERE user_id = %s AND qbank_topic_id = %s AND category_id = %s
        """, (user_id, topic_id, category_id))
        if cur.fetchone():
            return redirect(f"/qbank/topics/{topic_id}/categories/{category_id}/review")

        # Load questions of this (topic, category)
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

        # All categories for the chip bar
        cur.execute("""
            SELECT id, code, label, position
            FROM question_categories
            WHERE is_active = TRUE
            ORDER BY position
        """)
        all_categories = cur.fetchall()

    if selected_cats is None:
        selected_cats = [c["id"] for c in all_categories]

    return render_template(
        "qbank_question.html",
        topic=topic,
        category=category,
        questions=questions,
        notes=notes,
        bookmarks=bookmarks,
        review_mode=False,
        all_categories=all_categories,
        selected_cats=selected_cats,
    )


# ═══════════════════════════════════════════════════════════════
# TOPIC + CATEGORY → REVIEW (read-only)
# ═══════════════════════════════════════════════════════════════
@qbank_bp.route("/topics/<int:topic_id>/categories/<int:category_id>/review")
def qbank_category_review(topic_id, category_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    cats_param = request.args.get("cats")
    if cats_param:
        try:
            selected_cats = [int(x) for x in cats_param.split(",") if x.strip()]
        except ValueError:
            selected_cats = []
    else:
        selected_cats = None

    with db_cursor() as cur:
        # Load topic
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
            return "QBank topic not found", 404

        # Load category
        cur.execute("""
            SELECT id, code, label, position
            FROM question_categories
            WHERE id = %s
        """, (category_id,))
        category = cur.fetchone()
        if not category:
            return "Category not found", 404

        # Load questions
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

    return render_template(
        "qbank_question.html",
        topic=topic,
        category=category,
        questions=questions,
        notes=notes,
        bookmarks=bookmarks,
        review_mode=True,
        all_categories=all_categories,
        selected_cats=selected_cats,
    )


# ═══════════════════════════════════════════════════════════════
# MARK CATEGORY COMPLETE
# ═══════════════════════════════════════════════════════════════
@qbank_bp.route("/topics/<int:topic_id>/categories/<int:category_id>/complete", methods=["POST"])
def qbank_category_complete(topic_id, category_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, message="Not logged in"), 401

    # Read the request body
    data = request.get_json() or {}
    selected_cats = data.get("cats")          # list of ints or None (topic-wise mode)
    req_year = data.get("year")               # int or None (year-wise mode)
    req_type = data.get("type")               # str or None (year-wise mode)

    with db_cursor() as cur:
        # Verify topic
        cur.execute("SELECT id FROM qbank_topics WHERE id = %s", (topic_id,))
        if not cur.fetchone():
            return jsonify(success=False, message="Topic not found"), 404

        # Verify category
        cur.execute("SELECT id FROM question_categories WHERE id = %s", (category_id,))
        if not cur.fetchone():
            return jsonify(success=False, message="Category not found"), 400

        # ── Topic-wise completion (existing behaviour) ─────────
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

        # ── Year-wise completion (only if year + type passed) ──
        paper_completed = False
        if req_year and req_type:
            cur.execute("""
                SELECT s.goal_id, s.id AS subject_id
                FROM qbank_topics qt
                JOIN chapters c ON qt.chapter_id = c.id
                JOIN subjects s ON c.subject_id = s.id
                WHERE qt.id = %s
            """, (topic_id,))
            meta_row = cur.fetchone()

            if meta_row:
                from qbank_year_helpers import cascade_year_completion
                paper_completed = cascade_year_completion(
                    cur, user_id,
                    meta_row["goal_id"],
                    meta_row["subject_id"],
                    topic_id, category_id,
                    req_year, req_type
                )

        # Find next step in topic-wise traversal (only relevant for topic-wise mode)
        next_step = None
        if selected_cats is not None or not req_year:
            next_step = _find_next_step(cur, user_id, topic_id, category_id, selected_cats)

    # Build response
    papers_completed = []
    if paper_completed and req_year and req_type:
        papers_completed.append({"year": req_year, "type": req_type})

    return jsonify(
        success=True,
        next_step=next_step,
        paper_completed=paper_completed,
        papers_completed=papers_completed,
    )

# ═══════════════════════════════════════════════════════════════
# SAVE NOTES
# ═══════════════════════════════════════════════════════════════
@qbank_bp.route("/questions/<int:question_id>/note", methods=["POST"])
def qbank_save_note(question_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, message="Not logged in"), 401

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
@qbank_bp.route("/questions/<int:question_id>/bookmark", methods=["POST"])
def qbank_toggle_bookmark(question_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, message="Not logged in"), 401

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
# QBANK BOOKMARKS — subjects list
# ═══════════════════════════════════════════════════════════════
@qbank_bp.route("/bookmarks")
def qbank_bookmarks_home():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    with db_cursor() as cur:
        # QBank bookmarks grouped by subject
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

    return render_template("qbank_bookmark_subjects.html", subjects=subjects)


# ═══════════════════════════════════════════════════════════════
# QBANK BOOKMARKS — questions within a subject
# ═══════════════════════════════════════════════════════════════
@qbank_bp.route("/bookmarks/subject/<int:subject_id>")
def qbank_bookmarks_for_subject(subject_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    with db_cursor() as cur:
        # Subject
        cur.execute("SELECT id, name FROM subjects WHERE id = %s", (subject_id,))
        subject = cur.fetchone()
        if not subject:
            return "Subject not found", 404

        # All bookmarked QBank questions in this subject, with category info
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

    questions = [
        {
            "id": r["question_id"],
            "text": r["text"],
            "answer": r["answer"],
            "image_path": r["image_path"],
            "answer_image_path": r["answer_image_path"],
            "category_label": r["category_label"],
            "topic_name": r["topic_name"],
        }
        for r in rows
    ]

    return render_template(
        "qbank_bookmark_subject.html",
        subject=subject,
        questions=questions,
    )


# ═══════════════════════════════════════════════════════════════
# YEAR-WISE MODE
# ═══════════════════════════════════════════════════════════════

@qbank_bp.route("/years")
def qbank_years():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    # Optional subject filter (?subject=<id>)
    subject_filter = request.args.get("subject")
    try:
        subject_filter = int(subject_filter) if subject_filter else None
    except ValueError:
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
            return render_template(
                "qbank_years.html",
                goal=None,
                subjects=[],
                all_subjects=[],
                selected_subject=None,
            )

        goal_id = user["current_goal_id"]
        goal_name = user["goal_name"]

        # Subject list for the filter dropdown
        cur.execute("""
            SELECT id, name FROM subjects
            WHERE goal_id = %s
            ORDER BY id
        """, (goal_id,))
        all_subjects = cur.fetchall()

        # (subject, year, type) rows
        if subject_filter:
            cur.execute("""
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
                  AND s.id = %s
                GROUP BY s.id, s.name, q.exam_year, q.exam_type
                ORDER BY s.id,
                         q.exam_year DESC,
                         CASE q.exam_type
                             WHEN 'regular' THEN 1
                             WHEN 'supplementary' THEN 2
                             ELSE 3 END
            """, (goal_id, subject_filter))
        else:
            cur.execute("""
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
                GROUP BY s.id, s.name, q.exam_year, q.exam_type
                ORDER BY s.id,
                         q.exam_year DESC,
                         CASE q.exam_type
                             WHEN 'regular' THEN 1
                             WHEN 'supplementary' THEN 2
                             ELSE 3 END
            """, (goal_id,))
        rows = cur.fetchall()

        # Completed papers, scoped by subject
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

    subjects = list(subjects_map.values())

    selected_subject = None
    if subject_filter:
        for s in all_subjects:
            if s["id"] == subject_filter:
                selected_subject = s
                break

    return render_template(
        "qbank_years.html",
        goal={"id": goal_id, "name": goal_name},
        subjects=subjects,
        all_subjects=all_subjects,
        selected_subject=selected_subject,
    )


# ═══════════════════════════════════════════════════════════════
# YEAR → SUBJECT → TOPICS
# ═══════════════════════════════════════════════════════════════
@qbank_bp.route("/years/<int:year>/<exam_type>/subjects/<int:subject_id>/topics")
def qbank_year_subject_topics(year, exam_type, subject_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    if exam_type not in ("regular", "supplementary"):
        return "Invalid paper type", 404

    with db_cursor() as cur:
        cur.execute("SELECT current_goal_id FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user or not user["current_goal_id"]:
            return redirect("/qbank/years")
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
            return "Subject not found", 404

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
            return "No questions in this subject for this paper", 404

        # Categories per topic + completion for THIS paper + THIS subject
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

        # Is the paper done FOR THIS SUBJECT?
        cur.execute("""
            SELECT 1 FROM qbank_year_paper_completion
            WHERE user_id = %s AND goal_id = %s AND subject_id = %s
              AND exam_year = %s AND exam_type = %s
        """, (user_id, goal_id, subject_id, year, exam_type))
        is_completed = cur.fetchone() is not None

    return render_template(
        "qbank_year_topics.html",
        year=year,
        exam_type=exam_type,
        subject=subject,
        goal_name=subject["goal_name"],
        chapters=chapters,
        is_completed=is_completed,
    )


# ═══════════════════════════════════════════════════════════════
# YEAR → SUBJECT → TOPIC + CATEGORY → QUESTIONS
# ═══════════════════════════════════════════════════════════════
@qbank_bp.route("/years/<int:year>/<exam_type>/topics/<int:topic_id>/categories/<int:category_id>")
def qbank_year_category_questions(year, exam_type, topic_id, category_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    if exam_type not in ("regular", "supplementary"):
        return "Invalid paper type", 404

    with db_cursor() as cur:
        cur.execute("SELECT current_goal_id FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user or not user["current_goal_id"]:
            return redirect("/qbank/years")
        goal_id = user["current_goal_id"]

        # Load topic (with subject_id for back-link)
        cur.execute("""
            SELECT qt.id, qt.name, qt.access_level,
                   s.id AS subject_id, s.goal_id, g.name AS goal_name
            FROM qbank_topics qt
            JOIN chapters c ON qt.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            JOIN goals g ON s.goal_id = g.id
            WHERE qt.id = %s
        """, (topic_id,))
        topic = cur.fetchone()
        if not topic:
            return "Topic not found", 404

        # Load category
        cur.execute("""
            SELECT id, code, label, position
            FROM question_categories
            WHERE id = %s
        """, (category_id,))
        category = cur.fetchone()
        if not category:
            return "Category not found", 404

        # Already completed for this paper + subject?
        cur.execute("""
            SELECT 1 FROM qbank_topic_year_completion
            WHERE user_id = %s AND goal_id = %s AND subject_id = %s
              AND qbank_topic_id = %s
              AND category_id = %s AND exam_year = %s AND exam_type = %s
        """, (user_id, goal_id, topic["subject_id"], topic_id,
              category_id, year, exam_type))
        already_done = cur.fetchone() is not None

        # Load questions
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
            return "No questions in this section", 404

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

    return render_template(
        "qbank_year_question.html",
        year=year,
        exam_type=exam_type,
        topic=topic,
        category=category,
        questions=questions,
        notes=notes,
        bookmarks=bookmarks,
        review_mode=already_done,
    )