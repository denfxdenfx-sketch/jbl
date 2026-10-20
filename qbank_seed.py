# seed_qbank.py
from db import db_cursor


TOPICS = [
    # (goal, subject, chapter, topic_name, access_level, position)
    ("GATE", "Mathematics",      "Number System", "Divisibility — QBank",     "free", 1),
    ("GATE", "Mathematics",      "Algebra",       "Linear Equations — QBank", "free", 1),
    ("GATE", "Computer Science", "Data Structures","Arrays — QBank",          "paid", 1),
    ("NEET", "Physics",          "Mechanics",     "Kinematics — QBank",       "free", 1),
    ("CAT",  "Mathematics",      "Number System", "Divisibility — QBank",     "free", 1),
]

QUESTIONS = [
    # (goal, subject, chapter, topic_name, text, answer, position)
    (
        "GATE", "Mathematics", "Number System", "Divisibility — QBank",
        "Prove that a number is divisible by 3 if and only if the sum of its digits is divisible by 3.",
        "Let N = a₀ + 10a₁ + 100a₂ + ... Since 10 ≡ 1 (mod 3), every 10^k ≡ 1 (mod 3). So N ≡ a₀ + a₁ + a₂ + ... (mod 3). Therefore N ≡ 0 (mod 3) iff the digit sum ≡ 0 (mod 3).",
        1,
    ),
    (
        "GATE", "Mathematics", "Number System", "Divisibility — QBank",
        "State and prove the divisibility rule for 11.",
        "A number is divisible by 11 iff the alternating sum of its digits is divisible by 11. Since 10 ≡ -1 (mod 11), 10^k ≡ (-1)^k. So N ≡ a₀ - a₁ + a₂ - a₃ + ... (mod 11).",
        2,
    ),
    (
        "GATE", "Mathematics", "Number System", "Divisibility — QBank",
        "What is the largest 3-digit number divisible by both 8 and 12?",
        "LCM(8, 12) = 24. Largest 3-digit number divisible by 24 is floor(999 / 24) * 24 = 41 * 24 = 984.",
        3,
    ),
    (
        "GATE", "Mathematics", "Algebra", "Linear Equations — QBank",
        "Solve the system: 2x + 3y = 12, x - y = 1.",
        "From x - y = 1 → x = y + 1. Substitute: 2(y+1) + 3y = 12 → 5y = 10 → y = 2. Then x = 3. Solution: (3, 2).",
        1,
    ),
    (
        "GATE", "Mathematics", "Algebra", "Linear Equations — QBank",
        "When does a system of two linear equations have no solution?",
        "A system ax + by = c, dx + ey = f has no solution when a/d = b/e ≠ c/f. The lines are parallel and distinct.",
        2,
    ),
    (
        "GATE", "Computer Science", "Data Structures", "Arrays — QBank",
        "Explain why array access is O(1).",
        "Arrays store elements in contiguous memory. The address of element i is base + i * sizeof(element). This computation is constant time regardless of i.",
        1,
    ),
    (
        "GATE", "Computer Science", "Data Structures", "Arrays — QBank",
        "What is the time complexity of inserting at the beginning of an array? Why?",
        "O(n). Every existing element must be shifted right by one position to make room at index 0.",
        2,
    ),
    (
        "NEET", "Physics", "Mechanics", "Kinematics — QBank",
        "Derive the equation v = u + at for uniformly accelerated motion.",
        "Acceleration a = dv/dt → dv = a dt. Integrate from 0 to t: ∫dv = a∫dt → v - u = at → v = u + at.",
        1,
    ),
    (
        "NEET", "Physics", "Mechanics", "Kinematics — QBank",
        "A car accelerates from rest at 2 m/s² for 5 s. Find its final velocity and distance travelled.",
        "v = u + at = 0 + 2*5 = 10 m/s. s = ut + ½at² = 0 + ½*2*25 = 25 m.",
        2,
    ),
    (
        "CAT", "Mathematics", "Number System", "Divisibility — QBank",
        "Find the remainder when 7^100 is divided by 5.",
        "7 ≡ 2 (mod 5). 2^4 ≡ 1 (mod 5), cycle length 4. 100 mod 4 = 0 → 2^100 ≡ 2^4 ≡ 1 (mod 5). Remainder = 1.",
        1,
    ),
]


def seed_qbank():
    print("Seeding QBank...")

    # ── 1. Insert qbank_topics ────────────────────────────────
    topic_ids = {}
    with db_cursor() as cur:
        for goal, subject, chapter, tname, level, pos in TOPICS:
            cur.execute("""
                SELECT c.id
                FROM chapters c
                JOIN subjects s ON c.subject_id = s.id
                JOIN goals g ON s.goal_id = g.id
                WHERE g.name = %s AND s.name = %s AND c.name = %s
            """, (goal, subject, chapter))
            row = cur.fetchone()
            if not row:
                print(f"  [skip] chapter not found: {goal}/{subject}/{chapter}")
                continue
            chapter_id = row["id"]

            cur.execute("""
                INSERT INTO qbank_topics (chapter_id, name, access_level, position)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id
            """, (chapter_id, tname, level, pos))
            r = cur.fetchone()
            if r:
                topic_ids[(goal, subject, chapter, tname)] = r["id"]
            else:
                # already exists — fetch the id
                cur.execute("""
                    SELECT id FROM qbank_topics
                    WHERE chapter_id = %s AND name = %s
                """, (chapter_id, tname))
                topic_ids[(goal, subject, chapter, tname)] = cur.fetchone()["id"]

    print(f"  Topics: {len(topic_ids)} ensured")

    # ── 2. Insert qbank_questions ────────────────────────────
    inserted = 0
    with db_cursor() as cur:
        for goal, subject, chapter, tname, text, answer, pos in QUESTIONS:
            tid = topic_ids.get((goal, subject, chapter, tname))
            if not tid:
                continue
            cur.execute("""
                SELECT 1 FROM qbank_questions
                WHERE qbank_topic_id = %s AND text = %s
                LIMIT 1
            """, (tid, text))
            if cur.fetchone():
                continue
            cur.execute("""
                INSERT INTO qbank_questions (qbank_topic_id, text, answer, position)
                VALUES (%s, %s, %s, %s)
            """, (tid, text, answer, pos))
            inserted += 1

    print(f"  Questions inserted: {inserted}")
    print("✓ QBank seeding complete.")


if __name__ == "__main__":
    seed_qbank()