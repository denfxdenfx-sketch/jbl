import csv
import sys
sys.path.insert(0, '.')
from db import db_cursor

CSV_FILENAME = 'ophthalmology_qbank.csv'  # Ensure this matches your file name!
GOAL_NAME = 'NEET PG'
SUBJECT_NAME = 'Ophthalmology'

def main():
    print(f"🚀 Starting import from {CSV_FILENAME}...")
    
    with db_cursor() as cur:
        # 1. Get the Goal
        cur.execute("SELECT id FROM goals WHERE name = %s", (GOAL_NAME,))
        goal = cur.fetchone()
        if not goal:
            print(f"❌ Error: Goal '{GOAL_NAME}' not found in database.")
            return
        goal_id = goal['id']

        # 2. Get Category IDs (e.g., '10-marker' -> 2, '5-marker' -> 5)
        cur.execute("SELECT id, code FROM question_categories")
        cats = {r['code']: r['id'] for r in cur.fetchall()}

        # 3. Open CSV
        try:
            with open(CSV_FILENAME, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                count = 0
                
                for row in reader:
                    # Skip empty rows
                    if not row.get('Question') or not row['Question'].strip():
                        continue
                        
                    chapter_name = row['Chapter'].strip()
                    topic_name = row['Topic'].strip()
                    marks_str = row['Marks'].strip() # e.g., "10", "5", "15"
                    
                    # Map "10" -> "10-marker", "5" -> "5-marker"
                    cat_code = f"{marks_str}-marker" 
                    category_id = cats.get(cat_code)
                    
                    if not category_id:
                        print(f"⚠️ Skipping question: Category '{cat_code}' not found in DB.")
                        continue

                    # --- HIERARCHY CREATION ---
                    
                    # A. Subject
                    cur.execute("SELECT id FROM subjects WHERE name = %s AND goal_id = %s", (SUBJECT_NAME, goal_id))
                    subj = cur.fetchone()
                    if not subj:
                        cur.execute("INSERT INTO subjects (goal_id, name) VALUES (%s, %s) RETURNING id", (goal_id, SUBJECT_NAME))
                        subj_id = cur.fetchone()['id']
                    else:
                        subj_id = subj['id']

                    # B. Chapter
                    cur.execute("SELECT id FROM chapters WHERE name = %s AND subject_id = %s", (chapter_name, subj_id))
                    ch = cur.fetchone()
                    if not ch:
                        cur.execute("INSERT INTO chapters (subject_id, name, position) VALUES (%s, %s, 1) RETURNING id", (subj_id, chapter_name))
                        ch_id = cur.fetchone()['id']
                    else:
                        ch_id = ch['id']

                    # C. QBank Topic
                    cur.execute("SELECT id FROM qbank_topics WHERE name = %s AND chapter_id = %s", (topic_name, ch_id))
                    tp = cur.fetchone()
                    if not tp:
                        cur.execute("INSERT INTO qbank_topics (chapter_id, name, access_level, position) VALUES (%s, %s, 'free', 1) RETURNING id", (ch_id, topic_name))
                        tp_id = cur.fetchone()['id']
                    else:
                        tp_id = tp['id']

                    # --- INSERT QUESTION ---
                    cur.execute("""
                        INSERT INTO qbank_questions 
                        (qbank_topic_id, text, answer, category_id, position, exam_year, exam_type)
                        VALUES (%s, %s, %s, %s, %s, NULL, NULL)
                    """, (
                        tp_id, 
                        row['Question'].strip(), 
                        row['Answer'].strip(), 
                        category_id,
                        count + 1
                    ))
                    
                    count += 1
                    print(f"        ✅ Inserted Q{count} ({marks_str} marks): {row['Question'][:30]}...")

            print(f"\n🎉 Finished! Successfully imported {count} questions.")

        except FileNotFoundError:
            print(f"❌ Error: Could not find '{CSV_FILENAME}' in the container. Did you push it?")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()
