"""
seed_schema.py

Populates the database with test data for every table.
Idempotent — safe to run multiple times.
Clears table data first (in the correct order) then re-seeds.

Run from Railway shell:
    python3 seed_schema.py
"""

import sys
sys.path.insert(0, ".")

from db import db_cursor


def clean_all(cur):
    """Delete all rows in FK-safe order (children first)."""
    tables_in_order = [
        "qbank_topic_year_completion",
        "qbank_year_paper_completion",
        "qbank_section_completion",
        "user_qbank_notes",
        "user_qbank_bookmarks",
        "qbank_questions",
        "qbank_topics",
        "user_answers",
        "test_answer_drafts",
        "test_attempts",
        "test_questions",
        "tests",
        "test_topics",
        "user_bookmarks",
        "user_topic_progress",
        "user_tokens",
        "subscriptions",
        "plans",
        "users",
        "questions",
        "upload_batches",
        "topics",
        "chapters",
        "subjects",
        "question_categories",
        "goals",
        "admins",
    ]
    for t in tables_in_order:
        try:
            cur.execute(f"DELETE FROM {t}")
        except Exception:
            pass
    print("✅ Cleared all tables")


def seed_goals(cur):
    goals = [
        ("NEET PG",),
        ("FMGE",),
        ("USMLE",),
        ("INICET",),
    ]
    for (name,) in goals:
        cur.execute(
            "INSERT INTO goals (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
            (name,),
        )
    print(f"✅ Seeded {len(goals)} goals")


def seed_subjects(cur):
    cur.execute("SELECT id, name FROM goals")
    goals = {r["name"]: r["id"] for r in cur.fetchall()}

    subjects = [
        (goals["NEET PG"], "Anatomy"),
        (goals["NEET PG"], "Physiology"),
        (goals["NEET PG"], "Biochemistry"),
        (goals["NEET PG"], "Pathology"),
        (goals["NEET PG"], "Pharmacology"),
        (goals["NEET PG"], "Microbiology"),
        (goals["NEET PG"], "Forensic Medicine"),
        (goals["NEET PG"], "Social Medicine"),
        (goals["NEET PG"], "Internal Medicine"),
        (goals["NEET PG"], "Surgery"),
        (goals["FMGE"], "Anatomy"),
        (goals["FMGE"], "Physiology"),
    ]
    for goal_id, name in subjects:
        cur.execute(
            "INSERT INTO subjects (goal_id, name) VALUES (%s, %s)",
            (goal_id, name),
        )
    print(f"✅ Seeded {len(subjects)} subjects")


def seed_chapters(cur):
    cur.execute("SELECT id, name FROM subjects ORDER BY id")
    subjects = {r["name"]: r["id"] for r in cur.fetchall()}

    chapters = [
        ("Anatomy", "Upper Limb", 1),
        ("Anatomy", "Lower Limb", 2),
        ("Anatomy", "Thorax", 3),
        ("Anatomy", "Abdomen", 4),
        ("Anatomy", "Head and Neck", 5),
        ("Physiology", "Cardiovascular System", 1),
        ("Physiology", "Respiratory System", 2),
        ("Physiology", "Renal System", 3),
        ("Physiology", "Nervous System", 4),
        ("Biochemistry", "Carbohydrate Metabolism", 1),
        ("Biochemistry", "Lipid Metabolism", 2),
        ("Biochemistry", "Protein Metabolism", 3),
        ("Pathology", "Cell Injury", 1),
        ("Pathology", "Inflammation", 2),
        ("Pathology", "Neoplasia", 3),
        ("Pharmacology", "General Pharmacology", 1),
        ("Pharmacology", "Cardiovascular Drugs", 2),
        ("Microbiology", "Bacteriology", 1),
        ("Microbiology", "Virology", 2),
    ]
    count = 0
    for subj_name, chap_name, pos in chapters:
        sid = subjects.get(subj_name)
        if not sid:
            continue
        cur.execute(
            "INSERT INTO chapters (subject_id, name, position) VALUES (%s, %s, %s)",
            (sid, chap_name, pos),
        )
        count += 1
    print(f"✅ Seeded {count} chapters")


def seed_topics(cur):
    cur.execute("SELECT id, name FROM chapters")
    chapters = {r["name"]: r["id"] for r in cur.fetchall()}

    topics = [
        ("Upper Limb", "Brachial Plexus", "free", "both"),
        ("Upper Limb", "Axilla", "free", "both"),
        ("Upper Limb", "Arm and Cubital Fossa", "paid", "both"),
        ("Lower Limb", "Femoral Triangle", "paid", "both"),
        ("Lower Limb", "Popliteal Fossa", "paid", "both"),
        ("Thorax", "Mediastinum", "paid", "both"),
        ("Thorax", "Heart and Pericardium", "paid", "both"),
        ("Abdomen", "Inguinal Canal", "paid", "both"),
        ("Abdomen", "Kidneys and Ureters", "paid", "both"),
        ("Head and Neck", "Cranial Nerves", "paid", "both"),
        ("Head and Neck", "Thyroid Gland", "paid", "both"),
        ("Cardiovascular System", "Cardiac Cycle", "free", "both"),
        ("Cardiovascular System", "ECG Basics", "free", "both"),
        ("Cardiovascular System", "Blood Pressure Regulation", "paid", "both"),
        ("Respiratory System", "Mechanics of Breathing", "free", "both"),
        ("Respiratory System", "Gas Exchange", "paid", "both"),
        ("Renal System", "Glomerular Filtration", "paid", "both"),
        ("Renal System", "Tubular Transport", "paid", "both"),
        ("Nervous System", "Action Potential", "paid", "both"),
        ("Carbohydrate Metabolism", "Glycolysis", "free", "both"),
        ("Carbohydrate Metabolism", "TCA Cycle", "free", "both"),
        ("Lipid Metabolism", "Beta Oxidation", "paid", "both"),
        ("Protein Metabolism", "Urea Cycle", "paid", "both"),
        ("Cell Injury", "Necrosis and Apoptosis", "free", "both"),
        ("Inflammation", "Acute Inflammation", "paid", "both"),
        ("Neoplasia", "Tumor Markers", "paid", "both"),
        ("General Pharmacology", "Pharmacokinetics", "free", "both"),
        ("Cardiovascular Drugs", "Antihypertensives", "paid", "both"),
        ("Bacteriology", "Staphylococcus", "paid", "both"),
        ("Virology", "HIV", "paid", "both"),
    ]
    count = 0
    for chap_name, topic_name, access, ctx in topics:
        cid = chapters.get(chap_name)
        if not cid:
            continue
        cur.execute(
            """INSERT INTO topics (chapter_id, name, access_level, context)
               VALUES (%s, %s, %s, %s)""",
            (cid, topic_name, access, ctx),
        )
        count += 1
    print(f"✅ Seeded {count} topics")


def seed_admins(cur):
    # Password hash for "admin123" using werkzeug
    from werkzeug.security import generate_password_hash

    admins = [
        ("admin", "admin@example.com", "superadmin"),
        ("moderator", "mod@example.com", "admin"),
    ]
    for username, email, role in admins:
        cur.execute(
            """INSERT INTO admins (username, email, password_hash, role)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (username) DO NOTHING""",
            (username, email, generate_password_hash("admin123"), role),
        )
    print(f"✅ Seeded {len(admins)} admins")


def seed_users(cur):
    from werkzeug.security import generate_password_hash

    cur.execute("SELECT id FROM goals WHERE name = 'NEET PG'")
    goal_row = cur.fetchone()
    goal_id = goal_row["id"] if goal_row else None

    users = [
        ("alice@example.com", "+919000000001", "Alice", "Wong", goal_id),
        ("bob@example.com", "+919000000002", "Bob", "Kumar", goal_id),
        ("carol@example.com", "+919000000003", "Carol", "Patel", goal_id),
    ]
    for email, phone, first, last, goal in users:
        cur.execute(
            """INSERT INTO users
                   (email, phone_number, first_name, last_name,
                    password_hash, current_goal_id)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (email) DO NOTHING""",
            (
                email,
                phone,
                first,
                last,
                generate_password_hash("password123"),
                goal,
            ),
        )
    print(f"✅ Seeded {len(users)} users")


def seed_plans(cur):
    cur.execute("SELECT id, name FROM goals")
    goals = {r["name"]: r["id"] for r in cur.fetchall()}

    plans = [
        (goals["NEET PG"], "3 Months", 90, 16999),
        (goals["NEET PG"], "6 Months", 180, 29249),
        (goals["NEET PG"], "12 Months", 365, 34199),
        (goals["NEET PG"], "15 Months", 450, 39599),
        (goals["NEET PG"], "24 Months", 720, 50824),
        (goals["FMGE"], "3 Months", 90, 8999),
        (goals["FMGE"], "6 Months", 180, 14999),
    ]
    for goal_id, name, days, price in plans:
        cur.execute(
            """INSERT INTO plans (goal_id, name, duration_days, price, currency)
               VALUES (%s, %s, %s, %s, 'INR')""",
            (goal_id, name, days, price),
        )
    print(f"✅ Seeded {len(plans)} plans")


def seed_subscriptions(cur):
    cur.execute("SELECT id FROM users ORDER BY id")
    users = [r["id"] for r in cur.fetchall()]

    cur.execute(
        "SELECT id, goal_id, duration_days FROM plans ORDER BY id LIMIT 1"
    )
    plan = cur.fetchone()
    if not plan or not users:
        print("⚠️  Skipping subscriptions (no users or plans)")
        return

    from datetime import datetime, timedelta

    start = datetime.utcnow()
    end = start + timedelta(days=plan["duration_days"])

    for uid in users[:2]:
        cur.execute(
            """INSERT INTO subscriptions
                   (user_id, plan_id, goal_id, status,
                    current_period_start, current_period_end,
                    payment_provider, provider_sub_id)
               VALUES (%s, %s, %s, 'active', %s, %s, 'razorpay', %s)""",
            (
                uid,
                plan["id"],
                plan["goal_id"],
                start,
                end,
                f"sub_{uid}",
            ),
        )
    print(f"✅ Seeded 2 subscriptions")


def seed_test_topics(cur):
    topics = [
        ("Anatomy Basics", "Foundational anatomy concepts"),
        ("Physiology Essentials", "Core physiology principles"),
        ("Pathology Fundamentals", "Cell injury and inflammation"),
        ("Pharmacology Basics", "Drug classes and mechanisms"),
    ]
    for name, desc in topics:
        cur.execute(
            """INSERT INTO test_topics (name, description)
               VALUES (%s, %s)
               ON CONFLICT (name) DO NOTHING""",
            (name, desc),
        )
    print(f"✅ Seeded {len(topics)} test_topics")


def seed_tests(cur):
    cur.execute("SELECT id FROM goals WHERE name = 'NEET PG'")
    goal_row = cur.fetchone()
    if not goal_row:
        print("⚠️  Skipping tests (no goal)")
        return
    goal_id = goal_row["id"]

    cur.execute("SELECT id FROM test_topics ORDER BY id LIMIT 1")
    tt_row = cur.fetchone()
    test_topic_id = tt_row["id"] if tt_row else None

    tests = [
        (goal_id, test_topic_id, "Anatomy Mock Test 1", 180, 300, "free", True),
        (goal_id, test_topic_id, "Physiology Mock Test 1", 120, 200, "paid", True),
        (goal_id, test_topic_id, "Grand Test 1", 240, 400, "paid", False),
    ]
    for goal_id, tt_id, name, dur, marks, access, pub in tests:
        cur.execute(
            """INSERT INTO tests
                   (goal_id, test_topic_id, name, duration_minutes, total_marks,
                    access_level, is_published)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (goal_id, tt_id, name, dur, marks, access, pub),
        )
    print(f"✅ Seeded {len(tests)} tests")


def seed_questions(cur):
    cur.execute("SELECT id, name FROM topics ORDER BY id LIMIT 10")
    topics = cur.fetchall()

    cur.execute("SELECT id, username FROM admins ORDER BY id LIMIT 1")
    admin = cur.fetchone()

    samples = [
        ("Which of the following is a branch of the brachial plexus?",
         "Musculocutaneous", "Femoral", "Sciatic", "Obturator", "A", "The musculocutaneous nerve arises from the lateral cord of the brachial plexus."),
        ("The femoral triangle is bounded laterally by:",
         "Sartorius", "Adductor longus", "Inguinal ligament", "Pectineus", "A", "The lateral border of the femoral triangle is formed by the medial border of the sartorius muscle."),
        ("Which muscle is the primary flexor of the elbow?",
         "Biceps brachii", "Triceps brachii", "Brachioradialis", "Deltoid", "A", "The biceps brachii is the primary flexor of the elbow joint."),
        ("The SA node is located in:",
         "Right atrium", "Left atrium", "Right ventricle", "Left ventricle", "A", "The sinoatrial node is located in the upper part of the right atrium."),
        ("The normal resting heart rate is:",
         "60–100 bpm", "40–60 bpm", "100–120 bpm", "20–40 bpm", "A", "Normal resting heart rate is 60 to 100 beats per minute."),
    ]

    count = 0
    for topic in topics:
        tid = topic["id"]
        for i, s in enumerate(samples):
            cur.execute(
                """INSERT INTO questions
                       (topic_id, text, option_a, option_b, option_c, option_d,
                        correct_option, explanation, is_preview,
                        context, upload_batch_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE, 'both', NULL)""",
                (tid, *s[:7]),
            )
            count += 1
            if count >= 30:
                break
        if count >= 30:
            break
    print(f"✅ Seeded {count} questions")


def seed_question_categories(cur):
    cats = [
        ("15-marker", "15 Marker", 1),
        ("10-marker", "10 Marker", 2),
        ("short-notes", "Short Notes", 3),
        ("explain", "Explain Why", 4),
    ]
    for code, label, pos in cats:
        cur.execute(
            """INSERT INTO question_categories (code, label, position)
               VALUES (%s, %s, %s)
               ON CONFLICT (code) DO NOTHING""",
            (code, label, pos),
        )
    print(f"✅ Seeded {len(cats)} question_categories")


def seed_qbank_topics(cur):
    cur.execute("SELECT id, name FROM chapters")
    chapters = {r["name"]: r["id"] for r in cur.fetchall()}

    qbank_topics = [
        ("Upper Limb", "Brachial Plexus", "free", 1),
        ("Upper Limb", "Axilla", "free", 2),
        ("Upper Limb", "Arm and Cubital Fossa", "paid", 3),
        ("Lower Limb", "Femoral Triangle", "paid", 1),
        ("Lower Limb", "Popliteal Fossa", "paid", 2),
        ("Thorax", "Mediastinum", "paid", 1),
        ("Thorax", "Heart and Pericardium", "paid", 2),
        ("Abdomen", "Inguinal Canal", "paid", 1),
        ("Head and Neck", "Cranial Nerves", "paid", 1),
        ("Cardiovascular System", "Cardiac Cycle", "free", 1),
        ("Cardiovascular System", "ECG Basics", "free", 2),
        ("Respiratory System", "Mechanics of Breathing", "free", 1),
        ("Carbohydrate Metabolism", "Glycolysis", "free", 1),
        ("Cell Injury", "Necrosis and Apoptosis", "free", 1),
        ("General Pharmacology", "Pharmacokinetics", "free", 1),
    ]
    count = 0
    for chap_name, topic_name, access, pos in qbank_topics:
        cid = chapters.get(chap_name)
        if not cid:
            continue
        cur.execute(
            """INSERT INTO qbank_topics (chapter_id, name, access_level, position)
               VALUES (%s, %s, %s, %s)""",
            (cid, topic_name, access, pos),
        )
        count += 1
    print(f"✅ Seeded {count} qbank_topics")


def seed_qbank_questions(cur):
    cur.execute("SELECT id, name FROM qbank_topics ORDER BY id")
    qbank_topics = cur.fetchall()

    cur.execute("SELECT id, code FROM question_categories ORDER BY id")
    cats = {r["code"]: r["id"] for r in cur.fetchall()}

    samples = [
        ("Describe the branches of the brachial plexus.",
         "The brachial plexus is formed by the ventral rami of C5-T1. It divides into roots, trunks, divisions, cords, and branches. The main terminal branches are the musculocutaneous, axillary, radial, median, and ulnar nerves.",
         "15-marker", 2023, "regular"),
        ("What are the boundaries of the axilla?",
         "The axilla is bounded by the clavicle (apex), the first rib and upper border of the scapula, the humerus laterally, the chest wall medially, and the scapula posteriorly.",
         "short-notes", 2023, "regular"),
        ("Explain the mechanism of the cardiac cycle.",
         "The cardiac cycle consists of systole and diastole. During systole, the ventricles contract, ejecting blood into the aorta and pulmonary artery. During diastole, the ventricles relax and fill with blood from the atria.",
         "10-marker", 2023, "regular"),
        ("Write short notes on the femoral triangle.",
         "The femoral triangle is a subfascial space in the upper thigh. Its boundaries are the inguinal ligament (superior), sartorius (lateral), and adductor longus (medial). Contents: femoral nerve, artery, vein, and lymphatics (from lateral to medial).",
         "short-notes", 2023, "regular"),
        ("What is the significance of the SA node?",
         "The SA node is the natural pacemaker of the heart, generating impulses that set the heart rate. It is located in the right atrium near the opening of the superior vena cava.",
         "explain", 2023, "supplementary"),
        ("Describe the pathophysiology of cell injury.",
         "Cell injury results from various causes including hypoxia, toxins, infections, and physical agents. It disrupts ATP production, leading to membrane damage and cell death through necrosis or apoptosis.",
         "15-marker", 2023, "regular"),
        ("Explain the glycolysis pathway.",
         "Glycolysis is the breakdown of glucose to pyruvate, occurring in the cytoplasm. It yields 2 ATP and 2 NADH per glucose molecule. Under anaerobic conditions, pyruvate is converted to lactate.",
         "10-marker", 2023, "regular"),
    ]

    count = 0
    for topic in qbank_topics[:5]:
        tid = topic["id"]
        for text, answer, cat_code, year, etype in samples:
            cat_id = cats.get(cat_code)
            if not cat_id:
                continue
            cur.execute(
                """INSERT INTO qbank_questions
                       (qbank_topic_id, text, answer, category_id,
                        position, exam_year, exam_type)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (tid, text, answer, cat_id, count + 1, year, etype),
            )
            count += 1
            if count >= 30:
                break
        if count >= 30:
            break
    print(f"✅ Seeded {count} qbank_questions")


def seed_test_questions(cur):
    cur.execute("SELECT id FROM tests ORDER BY id")
    tests = [r["id"] for r in cur.fetchall()]
    cur.execute("SELECT id FROM questions ORDER BY id LIMIT 20")
    questions = [r["id"] for r in cur.fetchall()]

    count = 0
    for test_id in tests:
        for qid in questions:
            cur.execute(
                """INSERT INTO test_questions
                       (test_id, question_id, position, marks)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (test_id, question_id) DO NOTHING""",
                (test_id, qid, count + 1, 1),
            )
            count += 1
            if count >= 20:
                break
        if count >= 20:
            break
    print(f"✅ Seeded {count} test_questions")


def main():
    print("=" * 60)
    print("Seeding database")
    print("=" * 60)

    with db_cursor() as cur:
        clean_all(cur)
        seed_goals(cur)
        seed_subjects(cur)
        seed_chapters(cur)
        seed_topics(cur)
        seed_admins(cur)
        seed_users(cur)
        seed_plans(cur)
        seed_subscriptions(cur)
        seed_test_topics(cur)
        seed_tests(cur)
        seed_questions(cur)
        seed_question_categories(cur)
        seed_qbank_topics(cur)
        seed_qbank_questions(cur)
        seed_test_questions(cur)

    print()
    print("=" * 60)
    print("🎉 Database seeded successfully.")
    print("=" * 60)
    print()
    print("Test credentials:")
    print("  Admin: admin / admin123")
    print("  Users: alice@example.com / password123")
    print("         bob@example.com / password123")
    print("         carol@example.com / password123")


if __name__ == "__main__":
    main()
