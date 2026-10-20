# api_test.py
#
# JSON API mirror of the test flows in test.py.
# URL prefix: /api
#
# Covers:
#   - List tests for current goal
#   - Start / resume an attempt
#   - Fetch questions + drafts
#   - Save draft
#   - Submit attempt
#   - Review (per-subject breakdown + question-by-question)

from flask import Blueprint, jsonify, request, g
from db import db_cursor
from access import (
    has_access,
    get_test_access,
    completed_test_ids,
    test_is_completed,
)
from api_auth import api_login_required


api_test_bp = Blueprint("api_test", __name__, url_prefix="/api")


# ═══════════════════════════════════════════════════════════════
# LIST TESTS
# ═══════════════════════════════════════════════════════════════
@api_test_bp.route("/tests")
@api_login_required
def api_list_tests():
    user_id = g.user_id

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
                success=True,
                goal=None,
                tests=[],
            )

        goal_id = user["current_goal_id"]

        cur.execute("""
            SELECT
                t.id, t.name, t.description,
                t.duration_minutes, t.total_marks,
                t.access_level,
                t.is_published,
                tt.name AS test_topic_name
            FROM tests t
            LEFT JOIN test_topics tt ON t.test_topic_id = tt.id
            WHERE t.goal_id = %s AND t.is_published = TRUE
            ORDER BY tt.name NULLS LAST, t.id
        """, (goal_id,))
        tests = cur.fetchall()

    tests = get_test_access(user_id, goal_id, tests)
    completed = completed_test_ids(user_id, goal_id)

    tests_list = []
    for t in tests:
        tests_list.append({
            "id": t["id"],
            "name": t["name"],
            "description": t["description"],
            "duration_minutes": t["duration_minutes"],
            "total_marks": t["total_marks"],
            "access_level": t["access_level"],
            "is_published": t["is_published"],
            "test_topic_name": t["test_topic_name"],
            "locked": t.get("locked", False),
            "completed": t["id"] in completed,
        })

    return jsonify(
        success=True,
        goal={"id": goal_id, "name": user["goal_name"]},
        tests=tests_list,
    )


# ═══════════════════════════════════════════════════════════════
# START TEST
# ═══════════════════════════════════════════════════════════════
@api_test_bp.route("/tests/<int:test_id>/start", methods=["POST"])
@api_login_required
def api_start_test(test_id):
    user_id = g.user_id

    # Already completed → send to review of the latest submitted attempt
    if test_is_completed(user_id, test_id):
        with db_cursor() as cur:
            cur.execute("""
                SELECT id FROM test_attempts
                WHERE user_id = %s AND test_id = %s AND status = 'submitted'
                ORDER BY submitted_at DESC NULLS LAST
                LIMIT 1
            """, (user_id, test_id))
            attempt = cur.fetchone()
        if attempt:
            return jsonify(
                success=True,
                mode="review",
                attempt_id=attempt["id"],
            )
        # Fall through if no submitted attempt exists (edge case)

    with db_cursor() as cur:
        cur.execute("""
            SELECT id, name, goal_id, duration_minutes,
                   access_level, is_published
            FROM tests WHERE id = %s
        """, (test_id,))
        test = cur.fetchone()

    if not test:
        return jsonify(success=False, message="Test not found"), 404
    if not test["is_published"]:
        return jsonify(success=False, message="Test not available"), 404

    user_has_access = has_access(user_id, test["goal_id"])
    if test["access_level"] == "paid" and not user_has_access:
        return jsonify(success=False, message="Subscription required"), 403

    # Existing in-progress attempt?
    with db_cursor() as cur:
        cur.execute("""
            SELECT id FROM test_attempts
            WHERE user_id = %s AND test_id = %s AND status = 'in_progress'
            LIMIT 1
        """, (user_id, test_id))
        existing = cur.fetchone()

    if existing:
        return jsonify(
            success=True,
            mode="resume",
            attempt_id=existing["id"],
        )

    # Create new attempt
    with db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM test_questions WHERE test_id = %s",
            (test_id,),
        )
        total_q = cur.fetchone()["n"]

        cur.execute("""
            INSERT INTO test_attempts
                (user_id, test_id, status, started_at, expires_at,
                 last_activity_at, total_questions)
            VALUES (%s, %s, 'in_progress',
                    NOW(), NOW() + INTERVAL '1 minute' * %s,
                    NOW(), %s)
            RETURNING id
        """, (user_id, test_id, test["duration_minutes"], total_q))
        new_attempt = cur.fetchone()

    return jsonify(
        success=True,
        mode="new",
        attempt_id=new_attempt["id"],
    )


# ═══════════════════════════════════════════════════════════════
# RESUME INFO
# ═══════════════════════════════════════════════════════════════
@api_test_bp.route("/tests/attempts/<int:attempt_id>/resume")
@api_login_required
def api_resume_test(attempt_id):
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT ta.id, ta.status, ta.started_at, ta.expires_at,
                   ta.total_questions,
                   t.id AS test_id, t.name AS test_name, t.duration_minutes
            FROM test_attempts ta
            JOIN tests t ON ta.test_id = t.id
            WHERE ta.id = %s AND ta.user_id = %s
        """, (attempt_id, user_id))
        attempt = cur.fetchone()

        if not attempt:
            return jsonify(success=False, message="Attempt not found"), 404

        if attempt["status"] != "in_progress":
            return jsonify(
                success=True,
                mode="review",
                attempt_id=attempt_id,
            )

        cur.execute(
            "SELECT EXTRACT(EPOCH FROM (%s - NOW()))::INTEGER AS remaining",
            (attempt["expires_at"],),
        )
        remaining_seconds = cur.fetchone()["remaining"]

    if remaining_seconds <= 0:
        return jsonify(
            success=True,
            mode="expired",
            attempt_id=attempt_id,
        )

    return jsonify(
        success=True,
        mode="resume",
        attempt_id=attempt_id,
        attempt={
            "id": attempt["id"],
            "status": attempt["status"],
            "test_id": attempt["test_id"],
            "test_name": attempt["test_name"],
            "duration_minutes": attempt["duration_minutes"],
            "total_questions": attempt["total_questions"],
            "expires_at": attempt["expires_at"].isoformat()
                if attempt["expires_at"] else None,
        },
        remaining_seconds=remaining_seconds,
        remaining_minutes=remaining_seconds // 60,
    )


# ═══════════════════════════════════════════════════════════════
# NEW TEST CONFIRMATION
# ═══════════════════════════════════════════════════════════════
@api_test_bp.route("/tests/attempts/<int:attempt_id>/new")
@api_login_required
def api_new_test(attempt_id):
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT ta.id, ta.status, ta.started_at, ta.expires_at,
                   ta.total_questions,
                   t.id AS test_id, t.name AS test_name, t.duration_minutes,
                   t.total_marks
            FROM test_attempts ta
            JOIN tests t ON ta.test_id = t.id
            WHERE ta.id = %s AND ta.user_id = %s
        """, (attempt_id, user_id))
        attempt = cur.fetchone()

    if not attempt:
        return jsonify(success=False, message="Attempt not found"), 404

    if attempt["status"] != "in_progress":
        return jsonify(
            success=True,
            mode="review",
            attempt_id=attempt_id,
        )

    return jsonify(
        success=True,
        mode="new",
        attempt={
            "id": attempt["id"],
            "status": attempt["status"],
            "test_id": attempt["test_id"],
            "test_name": attempt["test_name"],
            "duration_minutes": attempt["duration_minutes"],
            "total_questions": attempt["total_questions"],
            "total_marks": attempt["total_marks"],
            "expires_at": attempt["expires_at"].isoformat()
                if attempt["expires_at"] else None,
        },
    )


# ═══════════════════════════════════════════════════════════════
# FETCH QUESTIONS + DRAFTS
# ═══════════════════════════════════════════════════════════════
@api_test_bp.route("/tests/attempts/<int:attempt_id>/questions")
@api_login_required
def api_attempt_questions(attempt_id):
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT ta.id, ta.status, ta.started_at, ta.expires_at,
                   ta.total_questions,
                   t.id AS test_id, t.name AS test_name,
                   t.duration_minutes, t.total_marks,
                   t.marks_per_correct, t.negative_marks,
                   t.show_feedback_during
            FROM test_attempts ta
            JOIN tests t ON ta.test_id = t.id
            WHERE ta.id = %s AND ta.user_id = %s
        """, (attempt_id, user_id))
        attempt = cur.fetchone()

        if not attempt:
            return jsonify(success=False, message="Attempt not found"), 404

        if attempt["status"] == "submitted":
            return jsonify(
                success=True,
                mode="review",
                attempt_id=attempt_id,
            )

        cur.execute(
            "SELECT NOW() > %s AS expired",
            (attempt["expires_at"],),
        )
        if cur.fetchone()["expired"]:
            return jsonify(
                success=True,
                mode="expired",
                attempt_id=attempt_id,
            )

        cur.execute("""
            SELECT q.id, q.text, q.option_a, q.option_b, q.option_c, q.option_d,
                   q.image_path,
                   tq.position, tq.marks
            FROM test_questions tq
            JOIN questions q ON tq.question_id = q.id
            WHERE tq.test_id = %s
            ORDER BY tq.position
        """, (attempt["test_id"],))
        questions = cur.fetchall()

        cur.execute("""
            SELECT question_id, selected_option, status, marked
            FROM test_answer_drafts
            WHERE test_attempt_id = %s
        """, (attempt_id,))
        drafts = {
            r["question_id"]: {
                "selected": r["selected_option"],
                "status": r["status"],
                "marked": r["marked"],
            }
            for r in cur.fetchall()
        }

        cur.execute("""
            SELECT question_id FROM user_bookmarks
            WHERE user_id = %s AND question_id IN (
                SELECT question_id FROM test_questions WHERE test_id = %s
            )
        """, (user_id, attempt["test_id"]))
        bookmarked_ids = [r["question_id"] for r in cur.fetchall()]

        cur.execute(
            "SELECT EXTRACT(EPOCH FROM (%s - NOW()))::INTEGER AS remaining",
            (attempt["expires_at"],),
        )
        remaining_seconds = cur.fetchone()["remaining"]

    start_index = 0
    for i, q in enumerate(questions):
        d = drafts.get(q["id"])
        if d is None or d["status"] == "unanswered":
            start_index = i
            break
    else:
        start_index = len(questions) - 1 if questions else 0

    # Notes keys become strings in JSON
    drafts_json = {str(k): v for k, v in drafts.items()}

    return jsonify(
        success=True,
        mode="quiz",
        attempt={
            "id": attempt["id"],
            "status": attempt["status"],
            "test_id": attempt["test_id"],
            "test_name": attempt["test_name"],
            "duration_minutes": attempt["duration_minutes"],
            "total_marks": attempt["total_marks"],
            "marks_per_correct": float(attempt["marks_per_correct"])
                if attempt["marks_per_correct"] is not None else None,
            "negative_marks": float(attempt["negative_marks"])
                if attempt["negative_marks"] is not None else None,
            "show_feedback_during": attempt["show_feedback_during"],
            "total_questions": attempt["total_questions"],
            "expires_at": attempt["expires_at"].isoformat()
                if attempt["expires_at"] else None,
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
                "position": q["position"],
                "marks": float(q["marks"]) if q["marks"] is not None else None,
            }
            for q in questions
        ],
        drafts=drafts_json,
        bookmarked_ids=bookmarked_ids,
        start_index=start_index,
        remaining_seconds=remaining_seconds,
    )


# ═══════════════════════════════════════════════════════════════
# SAVE DRAFT
# ═══════════════════════════════════════════════════════════════
@api_test_bp.route("/tests/attempts/<int:attempt_id>/save-draft", methods=["POST"])
@api_login_required
def api_save_draft(attempt_id):
    user_id = g.user_id
    data = request.get_json() or {}
    question_id = data.get("question_id")
    selected_option = data.get("selected_option")
    status = data.get("status", "unanswered")
    marked = data.get("marked", False)

    if not question_id:
        return jsonify(success=False, message="question_id required"), 400

    with db_cursor() as cur:
        cur.execute("""
            SELECT id, expires_at, status FROM test_attempts
            WHERE id = %s AND user_id = %s
        """, (attempt_id, user_id))
        attempt = cur.fetchone()

        if not attempt or attempt["status"] != "in_progress":
            return jsonify(success=False, message="Attempt not in progress"), 400

        cur.execute("SELECT NOW() > %s AS expired", (attempt["expires_at"],))
        if cur.fetchone()["expired"]:
            return jsonify(success=False, message="Time is up"), 400

        cur.execute("""
            INSERT INTO test_answer_drafts
                (test_attempt_id, question_id, selected_option, status, marked, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (test_attempt_id, question_id)
            DO UPDATE SET
                selected_option = EXCLUDED.selected_option,
                status = EXCLUDED.status,
                marked = EXCLUDED.marked,
                updated_at = NOW()
        """, (attempt_id, question_id, selected_option, status, marked))

        cur.execute(
            "UPDATE test_attempts SET last_activity_at = NOW() WHERE id = %s",
            (attempt_id,),
        )

    return jsonify(success=True)


# ═══════════════════════════════════════════════════════════════
# SUBMIT ATTEMPT
# ═══════════════════════════════════════════════════════════════
@api_test_bp.route("/tests/attempts/<int:attempt_id>/submit", methods=["POST"])
@api_login_required
def api_submit_attempt(attempt_id):
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT id, user_id, test_id, status, expires_at
            FROM test_attempts
            WHERE id = %s AND user_id = %s
        """, (attempt_id, user_id))
        attempt = cur.fetchone()

        if not attempt:
            return jsonify(success=False, message="Attempt not found"), 404

        if attempt["status"] in ("submitted", "expired"):
            return jsonify(
                success=True,
                mode="review",
                attempt_id=attempt_id,
            )

        if attempt["status"] != "in_progress":
            return jsonify(success=False, message="Cannot submit this attempt"), 400

        cur.execute("""
            SELECT id, name, marks_per_correct, negative_marks
            FROM tests WHERE id = %s
        """, (attempt["test_id"],))
        test = cur.fetchone()

        cur.execute("""
            SELECT
                tq.question_id,
                q.correct_option,
                tq.marks,
                COALESCE(d.selected_option, NULL) AS selected,
                COALESCE(d.status, 'unanswered') AS draft_status
            FROM test_questions tq
            JOIN questions q ON tq.question_id = q.id
            LEFT JOIN test_answer_drafts d
                ON d.question_id = tq.question_id
                AND d.test_attempt_id = %s
            WHERE tq.test_id = %s
            ORDER BY tq.position
        """, (attempt_id, attempt["test_id"]))
        rows = cur.fetchall()

    correct = 0
    wrong = 0
    skipped = 0
    score = 0.0

    with db_cursor() as cur:
        for r in rows:
            selected = r["selected"]
            correct_option = r["correct_option"]
            marks = float(r["marks"]) if r["marks"] is not None else 0.0

            if not selected:
                skipped += 1
                is_correct = False
                status_val = "skipped"
            elif selected == correct_option:
                correct += 1
                score += marks
                is_correct = True
                status_val = "answered"
            else:
                wrong += 1
                score -= float(test["negative_marks"])
                is_correct = False
                status_val = "answered"

            cur.execute("""
                INSERT INTO user_answers
                    (user_id, question_id, selected_option, is_correct,
                     context, test_attempt_id, status)
                VALUES (%s, %s, %s, %s, 'test', %s, %s)
            """, (user_id, r["question_id"], selected,
                  is_correct, attempt_id, status_val))

        cur.execute("""
            UPDATE test_attempts
            SET status = 'submitted',
                score = %s,
                correct_count = %s,
                wrong_count = %s,
                skipped_count = %s,
                submitted_at = NOW()
            WHERE id = %s
        """, (score, correct, wrong, skipped, attempt_id))

    return jsonify(
        success=True,
        mode="review",
        attempt_id=attempt_id,
        summary={
            "score": score,
            "correct": correct,
            "wrong": wrong,
            "skipped": skipped,
        },
    )


# ═══════════════════════════════════════════════════════════════
# REVIEW — Landing (per-subject breakdown)
# ═══════════════════════════════════════════════════════════════
@api_test_bp.route("/tests/attempts/<int:attempt_id>/review")
@api_login_required
def api_review_attempt(attempt_id):
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT ta.id, ta.test_id, ta.status, ta.score,
                   ta.correct_count, ta.wrong_count, ta.skipped_count,
                   ta.submitted_at,
                   t.name AS test_name, t.total_marks, t.negative_marks
            FROM test_attempts ta
            JOIN tests t ON ta.test_id = t.id
            WHERE ta.id = %s AND ta.user_id = %s
        """, (attempt_id, user_id))
        attempt = cur.fetchone()

        if not attempt:
            return jsonify(success=False, message="Attempt not found"), 404

        if attempt["status"] == "in_progress":
            return jsonify(
                success=True,
                mode="quiz",
                attempt_id=attempt_id,
            )

        cur.execute("""
            SELECT
                s.id AS subject_id,
                s.name AS subject_name,
                COUNT(*) FILTER (WHERE ua.is_correct) AS correct_count,
                COUNT(*) FILTER (
                    WHERE ua.is_correct = FALSE
                      AND ua.selected_option IS NOT NULL
                ) AS wrong_count,
                COUNT(*) FILTER (WHERE ua.selected_option IS NULL) AS skipped_count,
                COALESCE(SUM(tq.marks) FILTER (WHERE ua.is_correct), 0) AS positive_marks,
                COUNT(*) FILTER (
                    WHERE ua.is_correct = FALSE
                      AND ua.selected_option IS NOT NULL
                ) * %s AS negative_marks
            FROM user_answers ua
            JOIN questions q ON ua.question_id = q.id
            JOIN topics t ON q.topic_id = t.id
            JOIN chapters c ON t.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            LEFT JOIN test_questions tq
                ON tq.question_id = q.id
                AND tq.test_id = %s
            WHERE ua.test_attempt_id = %s
            GROUP BY s.id, s.name
            ORDER BY s.name
        """, (attempt["negative_marks"], attempt["test_id"], attempt_id))
        subjects = cur.fetchall()

    subjects_list = []
    for s in subjects:
        pos = float(s["positive_marks"] or 0)
        neg = float(s["negative_marks"] or 0)
        subjects_list.append({
            "subject_id": s["subject_id"],
            "subject_name": s["subject_name"],
            "correct_count": s["correct_count"],
            "wrong_count": s["wrong_count"],
            "skipped_count": s["skipped_count"],
            "positive_marks": pos,
            "negative_marks": neg,
            "score": pos - neg,
        })

    return jsonify(
        success=True,
        mode="review",
        attempt={
            "id": attempt["id"],
            "test_id": attempt["test_id"],
            "status": attempt["status"],
            "score": float(attempt["score"]) if attempt["score"] is not None else 0.0,
            "correct_count": attempt["correct_count"],
            "wrong_count": attempt["wrong_count"],
            "skipped_count": attempt["skipped_count"],
            "submitted_at": attempt["submitted_at"].isoformat()
                if attempt["submitted_at"] else None,
            "test_name": attempt["test_name"],
            "total_marks": float(attempt["total_marks"])
                if attempt["total_marks"] is not None else None,
            "negative_marks": float(attempt["negative_marks"])
                if attempt["negative_marks"] is not None else None,
        },
        subjects=subjects_list,
    )


# ═══════════════════════════════════════════════════════════════
# REVIEW — Answers (question-by-question)
# ═══════════════════════════════════════════════════════════════
@api_test_bp.route("/tests/attempts/<int:attempt_id>/review/answers")
@api_login_required
def api_review_answers(attempt_id):
    user_id = g.user_id

    with db_cursor() as cur:
        cur.execute("""
            SELECT ta.id, ta.test_id, ta.status, ta.score, ta.total_questions,
                   t.name AS test_name, t.total_marks
            FROM test_attempts ta
            JOIN tests t ON ta.test_id = t.id
            WHERE ta.id = %s AND ta.user_id = %s
        """, (attempt_id, user_id))
        attempt = cur.fetchone()

        if not attempt:
            return jsonify(success=False, message="Attempt not found"), 404

        if attempt["status"] == "in_progress":
            return jsonify(
                success=True,
                mode="quiz",
                attempt_id=attempt_id,
            )

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
                tq.position,
                tq.marks,
                COALESCE(ua.selected_option, NULL) AS user_answer,
                COALESCE(ua.is_correct, NULL) AS is_correct,
                COALESCE(ua.status, 'unanswered') AS answer_status,
                s.id AS subject_id,
                s.name AS subject_name,
                CASE WHEN ub.id IS NOT NULL THEN TRUE ELSE FALSE END AS bookmarked
            FROM test_questions tq
            JOIN questions q ON tq.question_id = q.id
            JOIN topics t ON q.topic_id = t.id
            JOIN chapters c ON t.chapter_id = c.id
            JOIN subjects s ON c.subject_id = s.id
            LEFT JOIN user_answers ua
                ON ua.question_id = q.id AND ua.test_attempt_id = %s
            LEFT JOIN user_bookmarks ub
                ON ub.question_id = q.id AND ub.user_id = %s
            WHERE tq.test_id = %s
            ORDER BY tq.position
        """, (attempt_id, user_id, attempt["test_id"]))
        rows = cur.fetchall()

    questions = []
    for r in rows:
        questions.append({
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
            "position": r["position"],
            "marks": float(r["marks"]) if r["marks"] is not None else None,
            "user_answer": r["user_answer"],
            "is_correct": r["is_correct"],
            "answer_status": r["answer_status"],
            "subject_id": r["subject_id"],
            "subject_name": r["subject_name"],
            "bookmarked": r["bookmarked"],
        })

    subject_map = {}
    for q in questions:
        subject_map[q["subject_id"]] = q["subject_name"]
    subjects = [
        {"id": sid, "name": name}
        for sid, name in sorted(subject_map.items())
    ]

    return jsonify(
        success=True,
        mode="review_answers",
        attempt={
            "id": attempt["id"],
            "test_id": attempt["test_id"],
            "status": attempt["status"],
            "score": float(attempt["score"]) if attempt["score"] is not None else 0.0,
            "total_questions": attempt["total_questions"],
            "test_name": attempt["test_name"],
            "total_marks": float(attempt["total_marks"])
                if attempt["total_marks"] is not None else None,
        },
        questions=questions,
        subjects=subjects,
    )