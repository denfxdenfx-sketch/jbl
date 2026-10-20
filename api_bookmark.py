# api_bookmark.py

from flask import Blueprint, jsonify, g
from db import db_cursor
from api_auth import api_login_required


api_bookmark_bp = Blueprint("api_bookmark", __name__, url_prefix="/api/bookmarks")


# ═══════════════════════════════════════════════════════════════
# ROUTE 1: Landing — list of subjects with bookmark counts
# ═══════════════════════════════════════════════════════════════

@api_bookmark_bp.route("")
@api_login_required
def api_bookmarks_home():
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT
                s.id AS subject_id,
                s.name AS subject_name,
                g.name AS goal_name,
                COUNT(ub.id) AS bookmark_count
            FROM user_bookmarks ub
            JOIN questions q ON ub.question_id = q.id
            JOIN topics t ON q.topic_id = t.id
            JOIN chapters c ON t.chapter_id = c.id
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
# ROUTE 2: Subject — bookmarked questions with user answers
# ═══════════════════════════════════════════════════════════════

@api_bookmark_bp.route("/subject/<int:subject_id>")
@api_login_required
def api_bookmarks_for_subject(subject_id):
    user_id = g.user_id

    with db_cursor() as cur:
        # Subject
        cur.execute("SELECT id, name FROM subjects WHERE id = %s", (subject_id,))
        subject = cur.fetchone()
        if not subject:
            return jsonify(success=False, message="Subject not found"), 404

        # Bookmarked questions with latest practice answer
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
                ua.is_correct,
                t.name AS topic_name
            FROM user_bookmarks ub
            JOIN questions q ON ub.question_id = q.id
            JOIN topics t ON q.topic_id = t.id
            JOIN chapters c ON t.chapter_id = c.id
            LEFT JOIN (
                SELECT DISTINCT ON (question_id)
                    question_id, selected_option, is_correct
                FROM user_answers
                WHERE user_id = %s AND context = 'practice'
                ORDER BY question_id, answered_at DESC
            ) ua ON ua.question_id = q.id
            WHERE ub.user_id = %s AND c.subject_id = %s
            ORDER BY ub.created_at DESC
        """, (user_id, user_id, subject_id))
        rows = cur.fetchall()

    return jsonify(
        success=True,
        subject={
            "id": subject["id"],
            "name": subject["name"],
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
                "topic_name": r["topic_name"],
            }
            for r in rows
        ],
    )