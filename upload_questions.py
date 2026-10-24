import csv
import sys
sys.path.insert(0, '.')
from db import db_cursor

# 1. CONFIGURATION
CSV_FILENAME = 'questions.csv'
SUBJECT_NAME = 'Ophthalmology' # Change this to match your DB
GOAL_NAME = 'NEET PG'          # Change this to match your DB

# Maps "10" -> category code "10-marker", etc.
CATEGORY_MAP = {
    '15': '15-marker',
    '10': '10-marker',
    'Short Notes': 'short-notes',
    'Explain': 'explain'
}

def get_or_create_hierarchy(cur, goal_id, chapter_name, topic_name):
    """Finds or creates the Subject, Chapter, and Topic, returning the topic_id."""
    
    # A. Get or Create Subject
    cur.execute("SELECT id FROM subjects WHERE name = %s AND goal_id = %s", (SUBJECT_NAME, goal_id))
    row = cur.fetchone()
    if row:
        subject_id = row['id']
    else:
        cur.execute("INSERT INTO subjects (goal_id, name) VALUES (%s, %s) RETURNING id", (goal_id, SUBJECT_NAME))
        subject_id = cur.fetchone()['id']
        print(f"  Created Subject: {SUBJECT_NAME}")

    # B. Get or Create Chapter
    cur.execute("SELECT id FROM chapters WHERE name = %s AND subject_id = %s", (chapter_name, subject_id))
    row = cur.fetchone()
    if row:
        chapter_id = row['id']
    else:
        cur.execute("INSERT INTO chapters (subject_id, name) VALUES (%s, %s) RETURNING id", (subject_id, chapter_name))
        chapter_id = cur.fetchone()['id']
        print(f"    Created Chapter: {chapter_name}")

    # C. Get or Create QBank Topic
    cur.execute("SELECT id FROM qbank_topics WHERE name = %s AND chapter_id = %s", (topic_name, chapter_id))
    row = cur.fetchone()
    if row:
        topic_id = row['id']
    else:
        cur.execute("INSERT INTO qbank_topics (chapter_id, name, access_level, position) VALUES (%s, %s, 'free', 1) RETURNING id", (chapter_id, topic_name))
        topic_id = cur.fetchone()['id']
        print(f"      Created Topic: {topic_name}")

    return topic_id

def main():
    print("Starting upload...")
    
    with db_cursor() as cur:
        # 1. Get the Goal ID
        cur.execute("SELECT id FROM goals WHERE name = %s", (GOAL_NAME,))
        goal_row = cur.fetchone()
        if not goal_row:
            print(f"Error: Goal '{GOAL_NAME}' not found in DB.")
            return
        goal_id = goal_row['id']

        # 2. Get Category IDs
        cur.execute("SELECT id, code FROM question_categories")
        cats = {r['code']: r['id'] for r in cur.fetchall()}

        # 3. Open the CSV
        with open(CSV_FILENAME, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            count = 0
            for row in reader:
                # Skip empty rows or headers
                if not row['Question'] or row['Question'].strip() == '': continue
                
                chapter_name = row['Chapter'].strip()
                topic_name = row['Topic'].strip()
                marks = row['Marks'].strip()
                
                # Figure out which category this belongs to
                cat_code = CATEGORY_MAP.get(marks)
                if not cat_code:
                    print(f"Skipping row (unknown marks type '{marks}')")
                    continue
                
                category_id = cats.get(cat_code)
                if not category_id:
                    print(f"Skipping row (category '{cat_code}' not found in DB)")
                    continue

                # Handle Year (Convert "General" to NULL, or int)
                exam_year = None
                exam_type = None
                if row['Year'].strip().isdigit():
                    exam_year = int(row['Year'].strip())
                    exam_type = 'regular'

                # Get the topic_id (creates chapter/topic if missing)
                topic_id = get_or_create_hierarchy(cur, goal_id, chapter_name, topic_name)

                # Insert the question
                cur.execute("""
                    INSERT INTO qbank_questions 
                        (qbank_topic_id, text, answer, category_id, position, exam_year, exam_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    topic_id, 
                    row['Question'].strip(), 
                    row['Answer'].strip(), 
                    category_id,
                    count + 1,
                    exam_year,
                    exam_type
                ))
                
                count += 1
                print(f"  Inserted Question {count}: {row['Question'][:30]}...")

    print(f"\n✅ Finished! Uploaded {count} questions.")

if __name__ == "__main__":
    main()
