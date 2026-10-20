def cascade_year_completion(cur, user_id, goal_id, subject_id, topic_id, category_id, exam_year, exam_type):
    """
    Called after a section is marked complete within a specific
    (subject, year, type) paper.

    Inserts per-section completion scoped to the subject, then checks
    if this SUBJECT's paper is complete.

    Returns True if this call completed the whole subject-paper.
    """
    # 1. Insert section completion scoped to subject + paper
    cur.execute("""
        INSERT INTO qbank_topic_year_completion
            (user_id, goal_id, subject_id, qbank_topic_id, category_id,
             exam_year, exam_type, completed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (user_id, goal_id, subject_id, qbank_topic_id, category_id,
                     exam_year, exam_type)
        DO NOTHING
    """, (user_id, goal_id, subject_id, topic_id, category_id, exam_year, exam_type))

    # 2. What sections does THIS SUBJECT need for THIS paper?
    cur.execute("""
        SELECT DISTINCT q.qbank_topic_id, q.category_id
        FROM qbank_questions q
        JOIN qbank_topics qt ON q.qbank_topic_id = qt.id
        JOIN chapters c ON qt.chapter_id = c.id
        WHERE c.subject_id = %s
          AND q.exam_year = %s
          AND q.exam_type = %s
    """, (subject_id, exam_year, exam_type))
    needed = {(r["qbank_topic_id"], r["category_id"]) for r in cur.fetchall()}

    # 3. What has the user done for THIS SUBJECT + paper?
    cur.execute("""
        SELECT qbank_topic_id, category_id
        FROM qbank_topic_year_completion
        WHERE user_id = %s AND goal_id = %s AND subject_id = %s
          AND exam_year = %s AND exam_type = %s
    """, (user_id, goal_id, subject_id, exam_year, exam_type))
    done = {(r["qbank_topic_id"], r["category_id"]) for r in cur.fetchall()}

    # 4. Complete paper for this subject?
    if needed and needed.issubset(done):
        cur.execute("""
            INSERT INTO qbank_year_paper_completion
                (user_id, goal_id, subject_id, exam_year, exam_type, completed_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (user_id, goal_id, subject_id, exam_year, exam_type)
            DO NOTHING
        """, (user_id, goal_id, subject_id, exam_year, exam_type))
        return True

    return False

def find_next_step_in_paper(cur, user_id, goal_id, year, exam_type,
                            current_topic_id, current_category_id):
    """
    Finds the next uncompleted (topic, category) in this paper.
    
    Priority:
    1. Next uncompleted category in the SAME topic.
    2. Next uncompleted category in the next topic of the SAME chapter.
    3. First uncompleted category in the next chapter.
    
    Returns {"topic_id": int, "category_id": int} or None if paper is done.
    """
    
    # 1. Fetch the entire ordered list of sections in this paper
    #    We use COALESCE to handle any NULL position values safely.
    cur.execute("""
        SELECT
            q.qbank_topic_id AS topic_id,
            q.category_id,
            c.id             AS chapter_id,
            c.position       AS chapter_position,
            qt.id            AS topic_id_order,
            qt.position      AS topic_position,
            qc.position      AS category_position
        FROM (
            SELECT DISTINCT qbank_topic_id, category_id
            FROM qbank_questions
            WHERE exam_year = %s AND exam_type = %s
        ) q
        JOIN qbank_topics qt ON q.qbank_topic_id = qt.id
        JOIN chapters c ON qt.chapter_id = c.id
        JOIN subjects s ON c.subject_id = s.id
        JOIN question_categories qc ON q.category_id = qc.id
        WHERE s.goal_id = %s
        ORDER BY
            COALESCE(c.position, 999999) ASC, c.id ASC,
            COALESCE(qt.position, 999999) ASC, qt.id ASC,
            COALESCE(qc.position, 999999) ASC, qc.id ASC
    """, (year, exam_type, goal_id))
    steps = cur.fetchall()

    if not steps:
        return None

    # 2. Locate where the current section sits in this list
    current_index = -1
    for i, s in enumerate(steps):
        if s["topic_id"] == current_topic_id and s["category_id"] == current_category_id:
            current_index = i
            break

    # 3. Load all completed sections for this user in this paper
    cur.execute("""
        SELECT qbank_topic_id, category_id
        FROM qbank_topic_year_completion
        WHERE user_id = %s AND goal_id = %s
          AND exam_year = %s AND exam_type = %s
    """, (user_id, goal_id, year, exam_type))
    completed_set = {(r["qbank_topic_id"], r["category_id"]) for r in cur.fetchall()}

    # 4. Walk forward from the current position.
    #    Because the SQL query is ordered exactly by Chapter -> Topic -> Category,
    #    simply returning the very first uncompleted item we find WILL naturally
    #    follow the priority (Same topic -> Next topic -> Next chapter).
    for i in range(current_index + 1, len(steps)):
        s = steps[i]
        key = (s["topic_id"], s["category_id"])
        
        # If it's not in the completed set, this is our next step
        if key not in completed_set:
            return {
                "topic_id": s["topic_id"],
                "category_id": s["category_id"],
            }

    # 5. If we reach the end of the list and found nothing, the paper is done.
    return None