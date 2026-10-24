"""
Import Ophthalmology Qbank CSV → Postgres
==========================================
Reads: ophthalmology_qbank.csv
Columns expected: Year, Question, Marks, Answer, Chapter, Topic

Hierarchy created (if missing):
    goals         → "MBBS WBUHS"
    subjects      → "Ophthalmology"
    chapters      → <Chapter from CSV>
    qbank_topics  → <Topic from CSV>

Then inserts into qbank_questions:
    text          = Question
    answer        = Answer
    category_id   = mapped from Marks
    exam_year     = NULL   (per your instruction)
    exam_type     = NULL
    position      = auto-increment per topic
    image_path    = NULL
    answer_image_path = NULL

Safety:
    - Skips a question if identical text already exists in that topic
    - Wraps everything in one transaction — rolls back on any error
    - --dry-run mode: no writes, just prints what would happen

Usage:
    python3 import_qbank.py ophthalmology_qbank.csv
    python3 import_qbank.py ophthalmology_qbank.csv --dry-run
"""

import os
import csv
import sys
import argparse

from db import get_connection


# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════

GOAL_NAME = "MBBS WBUHS"
SUBJECT_NAME = "Ophthalmology"

# How to map the Marks column → question_categories.code
# (tune these rules if your Marks values differ)
def marks_to_category(marks: str, question_text: str) -> str:
    m = (marks or "").replace(" ", "").lower()
    q = (question_text or "").lower()

    # Explain Why questions
    if q.startswith("explain why") or "explain why:" in q:
        return "explain"

    # 15-markers
    if m.startswith("15") or "15mark" in m:
        return "15-marker"

    # 10-markers
    if m.startswith("10") or "10mark" in m:
        return "10-marker"

    # Short notes (5, 2x5, 3x5 etc.)
    if "5" in m or "short" in q:
        return "short-notes"

    # Fallback
    return "short-notes"


# ═══════════════════════════════════════════════════════════════
# HELPERS — find-or-create
# ═══════════════════════════════════════════════════════════════

def get_or_create_goal(cur, name: str) -> int:
    cur.execute("SELECT id FROM goals WHERE name = %s;", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO goals (name) VALUES (%s) RETURNING id;", (name,))
    return cur.fetchone()[0]


def get_or_create_subject(cur, goal_id: int, name: str) -> int:
    cur.execute(
        "SELECT id FROM subjects WHERE goal_id = %s AND name = %s;",
        (goal_id, name),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO subjects (goal_id, name) VALUES (%s, %s) RETURNING id;",
        (goal_id, name),
    )
    return cur.fetchone()[0]


def get_or_create_chapter(cur, subject_id: int, name: str) -> int:
    cur.execute(
        "SELECT id FROM chapters WHERE subject_id = %s AND name = %s;",
        (subject_id, name),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO chapters (subject_id, name) VALUES (%s, %s) RETURNING id;",
        (subject_id, name),
    )
    return cur.fetchone()[0]


def get_or_create_topic(cur, chapter_id: int, name: str) -> int:
    cur.execute(
        "SELECT id FROM qbank_topics WHERE chapter_id = %s AND name = %s;",
        (chapter_id, name),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO qbank_topics (chapter_id, name) VALUES (%s, %s) RETURNING id;",
        (chapter_id, name),
    )
    return cur.fetchone()[0]


def get_category_id(cur, code: str) -> int:
    cur.execute("SELECT id FROM question_categories WHERE code = %s;", (code,))
    row = cur.fetchone()
    if row:
        return row[0]
    raise RuntimeError(
        f"question_categories has no row with code='{code}'. "
        f"Run init_db() first to seed categories."
    )


def question_exists(cur, topic_id: int, text: str) -> bool:
    cur.execute(
        "SELECT 1 FROM qbank_questions WHERE qbank_topic_id = %s AND text = %s LIMIT 1;",
        (topic_id, text),
    )
    return cur.fetchone() is not None


def next_position(cur, topic_id: int) -> int:
    cur.execute(
        "SELECT COALESCE(MAX(position), 0) + 1 FROM qbank_questions WHERE qbank_topic_id = %s;",
        (topic_id,),
    )
    return cur.fetchone()[0]


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file", help="Path to the CSV file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing to DB")
    args = parser.parse_args()

    if not os.path.isfile(args.csv_file):
        print(f"❌ CSV not found: {args.csv_file}")
        sys.exit(1)

    print(f"📂 Reading: {args.csv_file}")
    with open(args.csv_file, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("❌ CSV has no rows")
        sys.exit(1)

    print(f"   {len(rows)} rows found")
    print(f"   Columns: {list(rows[0].keys())}")

    required = {"Question", "Answer", "Marks", "Chapter", "Topic"}
    missing = required - set(rows[0].keys())
    if missing:
        print(f"❌ Missing columns: {missing}")
        sys.exit(1)

    if args.dry_run:
        print("\n🧪 DRY RUN — no writes will happen\n")

    conn = get_connection()
    cur = conn.cursor()

    try:
        # Fixed IDs (created once)
        goal_id = get_or_create_goal(cur, GOAL_NAME)
        subject_id = get_or_create_subject(cur, goal_id, SUBJECT_NAME)

        # Counters
        stats = {
            "created_questions": 0,
            "skipped_duplicates": 0,
            "skipped_empty": 0,
            "new_chapters": 0,
            "new_topics": 0,
        }

        # Cache chapter/topic IDs so we don't hit DB every row
        chapter_cache = {}
        topic_cache = {}

        for i, row in enumerate(rows, 1):
            q_text = (row.get("Question") or "").strip()
            a_text = (row.get("Answer") or "").strip()
            marks = (row.get("Marks") or "").strip()
            ch_name = (row.get("Chapter") or "").strip() or "Uncategorised"
            tp_name = (row.get("Topic") or "").strip() or ch_name

            if not q_text or not a_text:
                stats["skipped_empty"] += 1
                continue

            # Chapter
            if ch_name not in chapter_cache:
                existing = cur.execute(
                    "SELECT id FROM chapters WHERE subject_id = %s AND name = %s;",
                    (subject_id, ch_name),
                ) or cur.fetchone()
                if existing and cur.rowcount != 0:
                    pass
                cur.execute(
                    "SELECT id FROM chapters WHERE subject_id = %s AND name = %s;",
                    (subject_id, ch_name),
                )
                r = cur.fetchone()
                if r:
                    chapter_cache[ch_name] = r[0]
                else:
                    stats["new_chapters"] += 1
                    if not args.dry_run:
                        ch_id = get_or_create_chapter(cur, subject_id, ch_name)
                    else:
                        ch_id = -1
                    chapter_cache[ch_name] = ch_id

            chapter_id = chapter_cache[ch_name]

            # Topic
            key = (ch_name, tp_name)
            if key not in topic_cache:
                if not args.dry_run:
                    existing_topic = get_or_create_topic(cur, chapter_id, tp_name)
                    # detect new
                    cur.execute(
                        "SELECT COUNT(*) FROM qbank_topics WHERE chapter_id = %s AND name = %s;",
                        (chapter_id, tp_name),
                    )
                    topic_cache[key] = existing_topic
                else:
                    stats["new_topics"] += 1
                    topic_cache[key] = -1

            topic_id = topic_cache[key]

            # Category
            cat_code = marks_to_category(marks, q_text)
            cat_id = get_category_id(cur, cat_code)

            # Duplicate check
            if not args.dry_run and question_exists(cur, topic_id, q_text):
                stats["skipped_duplicates"] += 1
                continue
            elif args.dry_run:
                # pretend no dupe
                pass

            # Insert
            pos = next_position(cur, topic_id) if not args.dry_run else 0
            if not args.dry_run:
                cur.execute("""
                    INSERT INTO qbank_questions (
                        qbank_topic_id, text, answer, category_id,
                        exam_year, exam_type, position
                    ) VALUES (%s, %s, %s, %s, NULL, NULL, %s);
                """, (topic_id, q_text, a_text, cat_id, pos))

            stats["created_questions"] += 1

            if i % 50 == 0:
                print(f"   [{i}/{len(rows)}] processed "
                      f"(created={stats['created_questions']}, "
                      f"skipped={stats['skipped_duplicates']})")

        if args.dry_run:
            conn.rollback()
            print("\n🧪 DRY RUN complete — rolled back\n")
        else:
            conn.commit()
            print("\n✅ Committed\n")

        # Summary
        print("═══════════════════════════════════════════")
        print("  IMPORT SUMMARY")
        print("═══════════════════════════════════════════")
        print(f"  Goal                : {GOAL_NAME}")
        print(f"  Subject             : {SUBJECT_NAME}")
        print(f"  Rows in CSV         : {len(rows)}")
        print(f"  New questions added : {stats['created_questions']}")
        print(f"  Skipped (duplicates): {stats['skipped_duplicates']}")
        print(f"  Skipped (empty)     : {stats['skipped_empty']}")
        print(f"  New chapters        : {stats['new_chapters']}")
        print(f"  Unique topics used  : {len(topic_cache)}")
        print("═══════════════════════════════════════════")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ ERROR: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
