# seed.py

from db import db_cursor


def insert_one(sql, params=None):
    with db_cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


def insert_many(sql, params_list):
    results = []
    with db_cursor() as cur:
        for params in params_list:
            cur.execute(sql, params)
            results.append(cur.fetchone())
        return results


def seed():
    print("Seeding database...")

    # ═══════════════════════════════════════════════════════════
    # 1. GOALS
    # ═══════════════════════════════════════════════════════════
    gate = insert_one("INSERT INTO goals (name) VALUES (%s) RETURNING id, name", ("GATE",))
    neet = insert_one("INSERT INTO goals (name) VALUES (%s) RETURNING id, name", ("NEET",))
    cat  = insert_one("INSERT INTO goals (name) VALUES (%s) RETURNING id, name", ("CAT",))
    print(f"  Goals: {gate['name']}={gate['id']}, {neet['name']}={neet['id']}, {cat['name']}={cat['id']}")

    gate_id = gate["id"]
    neet_id = neet["id"]
    cat_id  = cat["id"]

    # ═══════════════════════════════════════════════════════════
    # 2. SUBJECTS
    # ═══════════════════════════════════════════════════════════
    # GATE subjects
    gate_math = insert_one(
        "INSERT INTO subjects (goal_id, name) VALUES (%s, %s) RETURNING id",
        (gate_id, "Mathematics"),
    )
    gate_cs = insert_one(
        "INSERT INTO subjects (goal_id, name) VALUES (%s, %s) RETURNING id",
        (gate_id, "Computer Science"),
    )

    # NEET subjects
    neet_physics = insert_one(
        "INSERT INTO subjects (goal_id, name) VALUES (%s, %s) RETURNING id",
        (neet_id, "Physics"),
    )
    neet_chemistry = insert_one(
        "INSERT INTO subjects (goal_id, name) VALUES (%s, %s) RETURNING id",
        (neet_id, "Chemistry"),
    )

    # CAT subjects
    cat_math = insert_one(
        "INSERT INTO subjects (goal_id, name) VALUES (%s, %s) RETURNING id",
        (cat_id, "Mathematics"),
    )
    cat_verbal = insert_one(
        "INSERT INTO subjects (goal_id, name) VALUES (%s, %s) RETURNING id",
        (cat_id, "Verbal Ability"),
    )
    cat_di = insert_one(
        "INSERT INTO subjects (goal_id, name) VALUES (%s, %s) RETURNING id",
        (cat_id, "Data Interpretation"),
    )
    cat_lr = insert_one(
        "INSERT INTO subjects (goal_id, name) VALUES (%s, %s) RETURNING id",
        (cat_id, "Logical Reasoning"),
    )
    print("  Subjects: 8 created")

    # ═══════════════════════════════════════════════════════════
    # 3. CHAPTERS
    # ═══════════════════════════════════════════════════════════
    def add_chapter(subject_id, name, position):
        return insert_one(
            "INSERT INTO chapters (subject_id, name, position) VALUES (%s, %s, %s) RETURNING id",
            (subject_id, name, position),
        )

    # GATE → Mathematics chapters
    chap_num  = add_chapter(gate_math["id"], "Number System", 1)
    chap_alg  = add_chapter(gate_math["id"], "Algebra", 2)
    chap_geo  = add_chapter(gate_math["id"], "Geometry", 3)
    chap_calc = add_chapter(gate_math["id"], "Calculus", 4)

    # GATE → Computer Science chapters
    chap_ds   = add_chapter(gate_cs["id"], "Data Structures", 1)
    chap_algo = add_chapter(gate_cs["id"], "Algorithms", 2)
    chap_dbms = add_chapter(gate_cs["id"], "DBMS", 3)

    # NEET → Physics chapters
    chap_mech = add_chapter(neet_physics["id"], "Mechanics", 1)
    chap_therm = add_chapter(neet_physics["id"], "Thermodynamics", 2)

    # NEET → Chemistry chapters
    chap_org  = add_chapter(neet_chemistry["id"], "Organic Chemistry", 1)
    chap_inorg = add_chapter(neet_chemistry["id"], "Inorganic Chemistry", 2)

    # CAT → Mathematics chapters
    cat_num  = add_chapter(cat_math["id"], "Number System", 1)
    cat_algebra = add_chapter(cat_math["id"], "Algebra", 2)
    cat_geom = add_chapter(cat_math["id"], "Geometry", 3)

    # CAT → Verbal Ability chapters
    cat_rc   = add_chapter(cat_verbal["id"], "Reading Comprehension", 1)
    cat_vocab = add_chapter(cat_verbal["id"], "Vocabulary", 2)

    # CAT → Data Interpretation chapters
    cat_charts = add_chapter(cat_di["id"], "Charts and Tables", 1)
    cat_graphs = add_chapter(cat_di["id"], "Graphs", 2)

    # CAT → Logical Reasoning chapters
    cat_series = add_chapter(cat_lr["id"], "Series", 1)
    cat_puzzles = add_chapter(cat_lr["id"], "Puzzles", 2)

    print("  Chapters: 20 created")

    # ═══════════════════════════════════════════════════════════
    # 4. TOPICS
    # ═══════════════════════════════════════════════════════════
    def add_topic(chapter_id, name, access_level="paid"):
        return insert_one(
            "INSERT INTO topics (chapter_id, name, access_level) VALUES (%s, %s, %s) RETURNING id",
            (chapter_id, name, access_level),
        )

    # GATE Mathematics → Number System
    t_div     = add_topic(chap_num["id"], "Divisibility Rules", "free")
    t_prime   = add_topic(chap_num["id"], "Prime Numbers", "free")
    t_lcm     = add_topic(chap_num["id"], "LCM and HCF", "paid")
    t_remain  = add_topic(chap_num["id"], "Remainders", "paid")

    # GATE Mathematics → Algebra
    t_linear  = add_topic(chap_alg["id"], "Linear Equations", "free")
    t_quad    = add_topic(chap_alg["id"], "Quadratic Equations", "paid")
    t_poly    = add_topic(chap_alg["id"], "Polynomials", "paid")

    # GATE Mathematics → Geometry
    t_tri     = add_topic(chap_geo["id"], "Triangles", "paid")
    t_circle  = add_topic(chap_geo["id"], "Circles", "paid")

    # GATE Computer Science → Data Structures
    t_array   = add_topic(chap_ds["id"], "Arrays", "free")
    t_linked  = add_topic(chap_ds["id"], "Linked Lists", "free")
    t_stack   = add_topic(chap_ds["id"], "Stacks and Queues", "paid")

    # GATE Computer Science → Algorithms
    t_sort    = add_topic(chap_algo["id"], "Sorting", "free")
    t_search  = add_topic(chap_algo["id"], "Searching", "paid")

    # NEET Physics → Mechanics
    t_kine    = add_topic(chap_mech["id"], "Kinematics", "free")
    t_newton  = add_topic(chap_mech["id"], "Newton's Laws", "free")

    # NEET Physics → Thermodynamics
    t_heat    = add_topic(chap_therm["id"], "Heat and Temperature", "paid")

    # NEET Chemistry → Organic
    t_hydro   = add_topic(chap_org["id"], "Hydrocarbons", "free")

    # CAT Mathematics → Number System
    cat_div   = add_topic(cat_num["id"], "Divisibility Rules", "free")
    cat_prime = add_topic(cat_num["id"], "Prime Numbers", "free")

    # CAT Mathematics → Algebra
    cat_linear = add_topic(cat_algebra["id"], "Linear Equations", "free")

    # CAT Verbal → Reading Comprehension
    cat_main  = add_topic(cat_rc["id"], "Main Idea", "free")
    cat_inf   = add_topic(cat_rc["id"], "Inference", "paid")

    # CAT Verbal → Vocabulary
    cat_syn   = add_topic(cat_vocab["id"], "Synonyms", "free")
    cat_ant   = add_topic(cat_vocab["id"], "Antonyms", "paid")

    # CAT Data Interpretation → Charts and Tables
    cat_tables = add_topic(cat_charts["id"], "Reading Tables", "free")
    cat_bar    = add_topic(cat_charts["id"], "Bar Charts", "paid")

    # CAT Logical Reasoning → Series
    cat_num_series  = add_topic(cat_series["id"], "Number Series", "free")
    cat_let_series  = add_topic(cat_series["id"], "Letter Series", "paid")

    print("  Topics: 27 created")

    # ═══════════════════════════════════════════════════════════
    # 5. QUESTIONS (MCQs)
    # ═══════════════════════════════════════════════════════════
    def add_question(topic_id, text, a, b, c, d, correct, explanation, is_preview):
        return insert_one(
            """INSERT INTO questions
                (topic_id, text, option_a, option_b, option_c, option_d,
                 correct_option, explanation, is_preview)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (topic_id, text, a, b, c, d, correct, explanation, is_preview),
        )

    # GATE Mathematics → Divisibility Rules
    add_question(t_div["id"], "Is 12 divisible by 3?", "Yes", "No", "Sometimes", "Never",
                 "A", "12 / 3 = 4, no remainder.", True)
    add_question(t_div["id"], "Is 17 divisible by 5?", "Yes", "No", "Sometimes", "Always",
                 "B", "17 / 5 leaves remainder 2.", True)
    add_question(t_div["id"], "Is 100 divisible by 4?", "Yes", "No", "Only if even", "Cannot tell",
                 "A", "100 / 4 = 25.", False)

    # GATE Mathematics → Prime Numbers
    add_question(t_prime["id"], "What is the smallest prime number?", "0", "1", "2", "3",
                 "C", "2 is the smallest and only even prime.", True)
    add_question(t_prime["id"], "Which of these is prime?", "4", "6", "9", "7",
                 "D", "7 has no divisors other than 1 and itself.", True)
    add_question(t_prime["id"], "How many primes are below 10?", "3", "4", "5", "6",
                 "B", "2, 3, 5, 7 → four primes.", False)

    # GATE Mathematics → LCM and HCF
    add_question(t_lcm["id"], "What is the LCM of 4 and 6?", "12", "24", "8", "16",
                 "A", "LCM(4,6) = 12.", True)
    add_question(t_lcm["id"], "What is the HCF of 18 and 24?", "3", "6", "9", "12",
                 "B", "HCF(18,24) = 6.", True)

    # GATE Mathematics → Linear Equations
    add_question(t_linear["id"], "Solve: 2x + 4 = 10", "x = 2", "x = 3", "x = 4", "x = 5",
                 "B", "2x = 6, so x = 3.", True)
    add_question(t_linear["id"], "Solve: x - 5 = 3", "x = 8", "x = 2", "x = -8", "x = 3",
                 "A", "x = 3 + 5 = 8.", True)

    # GATE Computer Science → Arrays
    add_question(t_array["id"], "What is the index of the first element in an array?",
                 "1", "0", "-1", "Depends on language",
                 "B", "Most languages use 0-based indexing.", True)
    add_question(t_array["id"], "Time to access an array element by index?",
                 "O(1)", "O(n)", "O(log n)", "O(n²)",
                 "A", "Array access is constant time.", True)

    # GATE Computer Science → Sorting
    add_question(t_sort["id"], "Which sort is O(n log n) on average?",
                 "Bubble Sort", "Insertion Sort", "Quick Sort", "Selection Sort",
                 "C", "Quick Sort averages O(n log n).", True)

    # NEET Physics → Kinematics
    add_question(t_kine["id"], "Unit of acceleration?", "m/s", "m/s²", "m²/s", "m/s³",
                 "B", "Acceleration is m/s².", True)

    # NEET Physics → Newton's Laws
    add_question(t_newton["id"], "Newton's first law is also called?",
                 "Law of Force", "Law of Inertia", "Law of Motion", "Law of Gravity",
                 "B", "First law: law of inertia.", True)

    # CAT Mathematics → Divisibility Rules
    add_question(cat_div["id"], "Is 15 divisible by 5?", "Yes", "No", "Sometimes", "Never",
                 "A", "15 / 5 = 3.", True)
    add_question(cat_div["id"], "Is 21 divisible by 7?", "Yes", "No", "Only if even", "Cannot tell",
                 "A", "21 / 7 = 3.", True)

    # CAT Mathematics → Prime Numbers
    add_question(cat_prime["id"], "Is 1 a prime number?", "Yes", "No", "Sometimes", "Only odd",
                 "B", "1 is not prime. Primes need two distinct divisors.", True)

    # CAT Verbal → Main Idea
    add_question(cat_main["id"], "The passage mainly discusses:",
                 "Weather", "Economy", "Sports", "Politics",
                 "B", "The passage focuses on economic trends.", True)

    # CAT Verbal → Synonyms
    add_question(cat_syn["id"], "Choose the synonym of 'happy':",
                 "Sad", "Joyful", "Angry", "Tired",
                 "B", "'Joyful' means happy.", True)

    # CAT Logical Reasoning → Number Series
    add_question(cat_num_series["id"], "Next in series: 2, 4, 8, 16, __",
                 "18", "20", "32", "24",
                 "C", "Each term doubles. 16 × 2 = 32.", True)

    print("  Questions: ~20 created")

    # ═══════════════════════════════════════════════════════════
    # 6. PLANS
    # ═══════════════════════════════════════════════════════════
    def add_plan(goal_id, name, duration_days, price):
        return insert_one(
            "INSERT INTO plans (goal_id, name, duration_days, price, currency) VALUES (%s, %s, %s, %s, 'INR') RETURNING id",
            (goal_id, name, duration_days, price),
        )

    # GATE plans
    add_plan(gate_id, "GATE 1 Month",  30,  500)
    add_plan(gate_id, "GATE 6 Months", 180, 2500)
    add_plan(gate_id, "GATE 1 Year",   365, 4500)

    # NEET plans
    add_plan(neet_id, "NEET 1 Month",  30,  600)
    add_plan(neet_id, "NEET 1 Year",   365, 5000)

    # CAT plans
    add_plan(cat_id, "CAT 1 Month",  30,  500)
    add_plan(cat_id, "CAT 6 Months", 180, 2500)
    add_plan(cat_id, "CAT 1 Year",   365, 4500)
    add_plan(cat_id, "CAT 2 Years",  730, 8000)

    print("  Plans: 9 created")

    # ═══════════════════════════════════════════════════════════
    # 7. TEST_TOPICS + TESTS
    # ═══════════════════════════════════════════════════════════
    def add_test_topic(name, description):
        return insert_one(
            "INSERT INTO test_topics (name, description) VALUES (%s, %s) RETURNING id",
            (name, description),
        )

    tt_chapter = add_test_topic("Chapter Tests", "Topic-wise tests")
    tt_mock    = add_test_topic("Mock Exams", "Full-length mock exams")
    tt_grand   = add_test_topic("Grand Tests", "Grand test series")

    def add_test(goal_id, test_topic_id, name, description, duration, total_marks,
                 marks_per_correct, negative_marks, access_level, is_published):
        return insert_one(
            """INSERT INTO tests
                (goal_id, test_topic_id, name, description,
                 duration_minutes, total_marks, marks_per_correct, negative_marks,
                 access_level, is_published, show_feedback_during)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE) RETURNING id""",
            (goal_id, test_topic_id, name, description, duration, total_marks,
             marks_per_correct, negative_marks, access_level, is_published),
        )

    gate_test_1 = add_test(gate_id, tt_chapter["id"], "GATE Number System Test",
                           "Basic test on number system.", 30, 20, 4, 1, "free", True)
    gate_test_2 = add_test(gate_id, tt_chapter["id"], "GATE Algebra Test",
                           "Algebra practice test.", 45, 40, 4, 1, "paid", True)
    gate_mock   = add_test(gate_id, tt_mock["id"], "GATE Mock Test 1",
                           "Full-length mock test.", 180, 200, 4, 1, "paid", True)

    cat_test_1  = add_test(cat_id, tt_chapter["id"], "CAT Number System Test",
                           "Number system test for CAT.", 30, 20, 4, 1, "free", True)
    cat_mock    = add_test(cat_id, tt_mock["id"], "CAT Mock Test 1",
                           "Full-length mock test.", 180, 200, 4, 1, "paid", True)

    print("  Test topics: 3, Tests: 5 created")

    # ═══════════════════════════════════════════════════════════
    # 8. TEST_QUESTIONS (attach questions to tests)
    # ═══════════════════════════════════════════════════════════
    def attach_questions(test_id, topic_ids):
        with db_cursor() as cur:
            cur.execute("""
                INSERT INTO test_questions (test_id, question_id, position, marks)
                SELECT %s, q.id, ROW_NUMBER() OVER (ORDER BY q.id), 4
                FROM questions q
                WHERE q.topic_id = ANY(%s)
            """, (test_id, topic_ids))

    # GATE Number System Test — questions from divisibility, primes, LCM topics
    attach_questions(gate_test_1["id"], [
        t_div["id"], t_prime["id"], t_lcm["id"]
    ])

    # GATE Algebra Test — questions from linear, quad, poly topics
    attach_questions(gate_test_2["id"], [
        t_linear["id"], t_quad["id"], t_poly["id"]
    ])

    # GATE Mock Test — everything (limited to questions we have)
    attach_questions(gate_mock["id"], [
        t_div["id"], t_prime["id"], t_lcm["id"],
        t_linear["id"], t_array["id"], t_sort["id"],
    ])

    # CAT Number System Test
    attach_questions(cat_test_1["id"], [
        cat_div["id"], cat_prime["id"]
    ])

    # CAT Mock Test
    attach_questions(cat_mock["id"], [
        cat_div["id"], cat_prime["id"], cat_linear["id"],
        cat_main["id"], cat_syn["id"], cat_num_series["id"],
    ])

    print("  Test questions attached")

    print("\n✓ Seeding complete.")


if __name__ == "__main__":
    seed()