cat > migrate_subject_completion.py << 'ENDOFFILE'
import sys
sys.path.insert(0, '.')
from db import db_cursor

def drop_all_unique_constraints(cur, table_name):
    cur.execute("""
        SELECT conname FROM pg_constraint
        WHERE conrelid = %s::regclass AND contype = 'u'
    """, (table_name,))
    for r in cur.fetchall():
        name = r["conname"]
        cur.execute(f'ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS "{name}"')
        print(f"    dropped: {name}")

def add_unique_constraint(cur, table_name, constraint_name, columns):
    cur.execute("SELECT 1 FROM pg_constraint WHERE conname = %s", (constraint_name,))
    if cur.fetchone():
        print(f"    already exists: {constraint_name}")
        return
    cols = ", ".join(columns)
    cur.execute(f'ALTER TABLE {table_name} ADD CONSTRAINT "{constraint_name}" UNIQUE ({cols})')
    print(f"    added: {constraint_name}")

def main():
    print("=" * 60)
    print("Subject-scoped year completion migration")
    print("=" * 60)

    with db_cursor() as cur:
        print()
        print("→ Adding subject_id to qbank_topic_year_completion...")
        cur.execute("""
            ALTER TABLE qbank_topic_year_completion
                ADD COLUMN IF NOT EXISTS subject_id INTEGER
                REFERENCES subjects(id) ON DELETE CASCADE;
        """)
        print("    ok")

        print()
        print("→ Adding subject_id to qbank_year_paper_completion...")
        cur.execute("""
            ALTER TABLE qbank_year_paper_completion
                ADD COLUMN IF NOT EXISTS subject_id INTEGER
                REFERENCES subjects(id) ON DELETE CASCADE;
        """)
        print("    ok")

        print()
        print("→ Dropping old unique constraints...")
        drop_all_unique_constraints(cur, "qbank_topic_year_completion")
        drop_all_unique_constraints(cur, "qbank_year_paper_completion")

        print()
        print("→ Clearing existing year completion rows...")
        cur.execute("DELETE FROM qbank_topic_year_completion")
        cur.execute("DELETE FROM qbank_year_paper_completion")
        print("    cleared")

        print()
        print("→ Adding new unique constraints...")
        add_unique_constraint(
            cur, "qbank_topic_year_completion",
            "qbank_topic_year_completion_unique",
            ["user_id", "goal_id", "subject_id", "qbank_topic_id",
             "category_id", "exam_year", "exam_type"],
        )
        add_unique_constraint(
            cur, "qbank_year_paper_completion",
            "qbank_year_paper_completion_unique",
            ["user_id", "goal_id", "subject_id", "exam_year", "exam_type"],
        )

        print()
        print("→ Verifying...")
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'qbank_topic_year_completion'
              AND column_name = 'subject_id'
        """)
        print("  topic_year.subject_id:",
              "EXISTS" if cur.fetchone() else "MISSING")

        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'qbank_year_paper_completion'
              AND column_name = 'subject_id'
        """)
        print("  year_paper.subject_id:",
              "EXISTS" if cur.fetchone() else "MISSING")

    print()
    print("Migration complete.")

if __name__ == "__main__":
    main()
