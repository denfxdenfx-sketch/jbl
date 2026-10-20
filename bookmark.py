# bookmark.py

from flask import Blueprint, render_template, session, redirect
from db import db_cursor

bookmark_bp = Blueprint("bookmark", __name__)


# ═══════════════════════════════════════════════════════════════
# ROUTE 1: Landing — list of subjects with bookmark counts
# ═══════════════════════════════════════════════════════════════

@bookmark_bp.route("/bookmarks")
def bookmarks_home():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    with db_cursor() as cur:
        # ← CHANGED: route through chapters
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

    return render_template("bookmark_subjects.html", subjects=subjects)


# ═══════════════════════════════════════════════════════════════
# ROUTE 2: Subject — stacked list + detail view
# ═══════════════════════════════════════════════════════════════

@bookmark_bp.route("/bookmarks/subject/<int:subject_id>")
def bookmarks_for_subject(subject_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    with db_cursor() as cur:
        # Load subject
        cur.execute("SELECT id, name FROM subjects WHERE id = %s", (subject_id,))
        subject = cur.fetchone()
        if not subject:
            return "Subject not found", 404

        # ← CHANGED: route through chapters
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
            "topic_name": r["topic_name"],
        }
        for r in rows
    ]

    return render_template(
        "bookmark_subject.html",
        subject=subject,
        questions=questions,
    )