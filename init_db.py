import psycopg2
from db import DB_CONFIG           # ← import from db.py, don't define here

from psycopg2.extras import RealDictCursor


def get_connection():
    """Open a Postgres connection."""
    return psycopg2.connect(**DB_CONFIG)


def init_db():
    """Create all tables if they don't exist."""
    conn = get_connection()
    cur = conn.cursor()

    # ═══════════════════════════════════════════════════════════════
    # 1. GOALS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE
        );
    """)
    print("[database] goals table ready")

    # ═══════════════════════════════════════════════════════════════
    # 2. SUBJECTS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id SERIAL PRIMARY KEY,
            goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_subjects_goal ON subjects(goal_id);
    """)
    print("[database] subjects table ready")

    # ═══════════════════════════════════════════════════════════════
    # CHAPTERS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chapters (
        id SERIAL PRIMARY KEY,
        subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
        name VARCHAR(100) NOT NULL,
        position INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_chapters_subject ON chapters(subject_id);
    """)
    print("[database] chapters table ready")

    # ═══════════════════════════════════════════════════════════════
    # 3. TOPICS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            id SERIAL PRIMARY KEY,
            chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            access_level VARCHAR(20) NOT NULL DEFAULT 'paid'
                CHECK (access_level IN ('free', 'paid')),
            context VARCHAR(20) NOT NULL DEFAULT 'both'
                CHECK (context IN ('practice', 'test', 'both'))
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_topics_chapter ON topics(chapter_id);
    """)
    print("[database] topics table ready")

    # ═══════════════════════════════════════════════════════════════
    # 4. ADMINS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id SERIAL PRIMARY KEY,
            username VARCHAR(80) NOT NULL UNIQUE,
            email VARCHAR(120) NOT NULL UNIQUE,
            password_hash VARCHAR(200) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'admin'
                CHECK (role IN ('admin', 'superadmin')),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            last_login_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    print("[database] admins table ready")

    # ═══════════════════════════════════════════════════════════════
    # 5. UPLOAD_BATCHES
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS upload_batches (
            id SERIAL PRIMARY KEY,
            admin_id INTEGER NOT NULL REFERENCES admins(id),
            filename VARCHAR(255) NOT NULL,
            target_topic_id INTEGER REFERENCES topics(id),
            inserted_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'completed'
                CHECK (status IN ('processing', 'completed', 'failed', 'rolled_back')),
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_batches_admin ON upload_batches(admin_id);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_batches_topic ON upload_batches(target_topic_id);
    """)
    print("[database] upload_batches table ready")

    # ═══════════════════════════════════════════════════════════════
    # 6. QUESTIONS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY,
            topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
            text TEXT NOT NULL,
            option_a VARCHAR(500) NOT NULL,
            option_b VARCHAR(500) NOT NULL,
            option_c VARCHAR(500) NOT NULL,
            option_d VARCHAR(500) NOT NULL,
            correct_option CHAR(1) NOT NULL
                CHECK (correct_option IN ('A', 'B', 'C', 'D')),
            explanation TEXT,
            is_preview BOOLEAN NOT NULL DEFAULT FALSE,
            image_path VARCHAR(500),                      -- NEW
            explanation_image_path VARCHAR(500),          -- NEW
            context VARCHAR(20) NOT NULL DEFAULT 'both'
            CHECK (context IN ('practice', 'test', 'both')),
            upload_batch_id INTEGER REFERENCES upload_batches(id),
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_questions_topic ON questions(topic_id);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_questions_preview ON questions(is_preview);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_questions_batch ON questions(upload_batch_id);
    """)
    print("[database] questions table ready")

    # ═══════════════════════════════════════════════════════════════
    # 9. USERS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(80) ,
            email VARCHAR(120) NOT NULL UNIQUE,
            phone_number VARCHAR(20),
            password_hash VARCHAR(200),
            first_name VARCHAR(80),
            last_name VARCHAR(80),
            year_of_study VARCHAR(20),
            current_goal_id INTEGER REFERENCES goals(id),
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_goal ON users(current_goal_id);
    """)
    print("[database] users table ready")

    # ═══════════════════════════════════════════════════════════════
    # 10. PLANS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id SERIAL PRIMARY KEY,
            goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            duration_days INTEGER NOT NULL,
            price NUMERIC(10,2) NOT NULL,
            currency VARCHAR(3) DEFAULT 'INR'
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_plans_goal ON plans(goal_id);
    """)
    print("[database] plans table ready")

    # ═══════════════════════════════════════════════════════════════
    # 11. SUBSCRIPTIONS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            plan_id INTEGER NOT NULL REFERENCES plans(id),
            goal_id INTEGER NOT NULL REFERENCES goals(id),
            status VARCHAR(20) NOT NULL DEFAULT 'active'
                CHECK (status IN (
                    'trialing', 'active', 'past_due',
                    'canceling', 'canceled', 'expired'
                )),
            current_period_start TIMESTAMP NOT NULL,
            current_period_end TIMESTAMP NOT NULL,
            cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
            canceled_at TIMESTAMP,
            trial_start TIMESTAMP,
            trial_end TIMESTAMP,
            payment_provider VARCHAR(20),
            provider_sub_id VARCHAR(120),
            provider_customer_id VARCHAR(120),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_subs_user_goal
        ON subscriptions(user_id, goal_id);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_subs_status_end
        ON subscriptions(status, current_period_end);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_subs_provider_sub
        ON subscriptions(provider_sub_id);
    """)
    # Partial index for the fast has_access lookup
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_subs_active_lookup
        ON subscriptions(user_id, goal_id, current_period_end)
        WHERE status IN ('active', 'trialing', 'past_due', 'canceling');
    """)
    print("[database] subscriptions table ready")

    #33333 test databse creatiion

    # ═══════════════════════════════════════════════════════════════
    # 7. TESTS
    # ═══════════════════════════════════════════════════════════════
    # ═══════════════════════════════════════════════════════════════
    # TEST_TOPICS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS test_topics (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_test_topics_name ON test_topics(name);
    """)
    print("[database] test_topics table ready")

    # ═══════════════════════════════════════════════════════════════
    # TESTS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tests (
            id SERIAL PRIMARY KEY,
            goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
            test_topic_id INTEGER REFERENCES test_topics(id) ON DELETE SET NULL,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            duration_minutes INTEGER NOT NULL,
            total_marks INTEGER NOT NULL,
            marks_per_correct NUMERIC(4,2) NOT NULL DEFAULT 1,
            negative_marks NUMERIC(4,2) NOT NULL DEFAULT 0,
            access_level VARCHAR(20) NOT NULL DEFAULT 'paid'
                CHECK (access_level IN ('free', 'paid')),
            is_published BOOLEAN NOT NULL DEFAULT FALSE,
            show_feedback_during BOOLEAN NOT NULL DEFAULT FALSE,
            created_by INTEGER REFERENCES admins(id),
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_tests_goal ON tests(goal_id);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_tests_test_topic ON tests(test_topic_id);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_tests_published
        ON tests(goal_id) WHERE is_published = TRUE;
    """)
    print("[database] tests table created/ready")

    # ═══════════════════════════════════════════════════════════════
    # 8. TEST_QUESTIONS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS test_questions (
            id SERIAL PRIMARY KEY,
            test_id INTEGER NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
            question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            marks NUMERIC(4,2) NOT NULL DEFAULT 1,
            UNIQUE(test_id, question_id)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_test_questions_test ON test_questions(test_id);
    """)
    print("[database] test_questions table ready")

    # ═══════════════════════════════════════════════════════════════
    # 9. TEST_ATTEMPTS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS test_attempts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            test_id INTEGER NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'in_progress'
                CHECK (status IN ('in_progress', 'submitted', 'abandoned', 'expired')),
            started_at TIMESTAMP NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMP NOT NULL,
            submitted_at TIMESTAMP,
            last_activity_at TIMESTAMP NOT NULL DEFAULT NOW(),
            score NUMERIC(6,2),
            correct_count INTEGER,
            wrong_count INTEGER,
            skipped_count INTEGER,
            total_questions INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_attempts_user ON test_attempts(user_id);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_attempts_test ON test_attempts(test_id);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_attempts_user_test ON test_attempts(user_id, test_id);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_attempts_in_progress
        ON test_attempts(user_id, test_id) WHERE status = 'in_progress';
    """)
    print("[database] test_attempts table ready")

    # ═══════════════════════════════════════════════════════════════
    # 13. USER_ANSWERS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_answers (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            selected_option CHAR(1) CHECK (selected_option IN ('A', 'B', 'C', 'D')),
            is_correct BOOLEAN NOT NULL,
            context VARCHAR(20) NOT NULL DEFAULT 'practice'
                CHECK (context IN ('practice', 'test')),
            test_attempt_id INTEGER REFERENCES test_attempts(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'answered'
                CHECK (status IN ('answered', 'skipped', 'marked_for_review')),
            answered_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_answers_user
        ON user_answers(user_id);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_answers_user_question
        ON user_answers(user_id, question_id);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_answers_user_time
        ON user_answers(user_id, answered_at);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_answers_attempt
        ON user_answers(test_attempt_id);
    """)
    print("[database] user_answers table ready")

    # ═══════════════════════════════════════════════════════════════
    # 14. USER_TOPIC_PROGRESS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_topic_progress (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'not_started'
                CHECK (status IN ('not_started', 'in_progress', 'completed')),
            correct_count INTEGER NOT NULL DEFAULT 0,
            attempted_count INTEGER NOT NULL DEFAULT 0,
            completed_at TIMESTAMP,
            UNIQUE(user_id, topic_id)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_progress_user
        ON user_topic_progress(user_id);
    """)
    print("[database] user_topic_progress table ready")

    # ═══════════════════════════════════════════════════════════════
    # 15. USER_BOOKMARKS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_bookmarks (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            source VARCHAR(20) NOT NULL DEFAULT 'practice'
                CHECK (source IN ('practice', 'test', 'review')),
            test_attempt_id INTEGER REFERENCES test_attempts(id) ON DELETE SET NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, question_id)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_bookmarks_user
        ON user_bookmarks(user_id);
    """)
    print("[database] user_bookmarks table ready")

    # ═══════════════════════════════════════════════════════════════
    # USER_TOKENS (mobile sessions)
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token VARCHAR(128) NOT NULL UNIQUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMP NOT NULL,
            last_used_at TIMESTAMP
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_tokens_token
        ON user_tokens(token);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_tokens_user
        ON user_tokens(user_id);
    """)
    print("[database] user_tokens table ready")












    # ═══════════════════════════════════════════════════════════════
    # 16. ADMIN_AUDIT_LOG
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_audit_log (
            id SERIAL PRIMARY KEY,
            admin_id INTEGER NOT NULL REFERENCES admins(id),
            action VARCHAR(50) NOT NULL,
            target_table VARCHAR(50),
            target_id INTEGER,
            old_value JSONB,
            new_value JSONB,
            ip_address VARCHAR(45),
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_admin
        ON admin_audit_log(admin_id);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_target
        ON admin_audit_log(target_table, target_id);
    """)
    print("[database] admin_audit_log table ready")

    # ═══════════════════════════════════════════════════════════════
    # 10. TEST_ANSWER_DRAFTS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS test_answer_drafts (
            id SERIAL PRIMARY KEY,
            test_attempt_id INTEGER NOT NULL REFERENCES test_attempts(id) ON DELETE CASCADE,
            question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            selected_option CHAR(1) CHECK (selected_option IN ('A', 'B', 'C', 'D')),
            status VARCHAR(20) NOT NULL DEFAULT 'unanswered'
                CHECK (status IN ('unanswered', 'answered', 'skipped')),
            marked BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(test_attempt_id, question_id)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_drafts_attempt ON test_answer_drafts(test_attempt_id);
    """)
    print("[database] test_answer_drafts table ready")

    # ═══════════════════════════════════════════════════════════════
    # 17. QBANK_TOPICS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS qbank_topics (
            id SERIAL PRIMARY KEY,
            chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
            name VARCHAR(200) NOT NULL,
            access_level VARCHAR(20) NOT NULL DEFAULT 'paid'
                CHECK (access_level IN ('free', 'paid')),
            position INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_qbank_topics_chapter
        ON qbank_topics(chapter_id);
    """)
    print("[database] qbank_topics table ready")

    # ═══════════════════════════════════════════════════════════════
    # QUESTION_CATEGORIES (lookup table)
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS question_categories (
            id SERIAL PRIMARY KEY,
            code VARCHAR(30) NOT NULL UNIQUE,
            label VARCHAR(80) NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE
        );
    """)
    cur.execute("""
        INSERT INTO question_categories (code, label, position) VALUES
            ('15-marker',   '15 Marker',   1),
            ('10-marker',   '10 Marker',   2),
            ('short-notes', 'Short Notes', 3),
            ('explain',     'Explain Why', 4)
        ON CONFLICT (code) DO NOTHING;
    """)
    print("[database] question_categories table ready")










    # ═══════════════════════════════════════════════════════════════
    # QBANK_QUESTIONS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS qbank_questions (
            id SERIAL PRIMARY KEY,
            qbank_topic_id INTEGER NOT NULL REFERENCES qbank_topics(id) ON DELETE CASCADE,
            text TEXT NOT NULL,
            answer TEXT NOT NULL,
            category_id INTEGER NOT NULL REFERENCES question_categories(id),
            image_path VARCHAR(500),
            answer_image_path VARCHAR(500),
            position INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_qbank_questions_topic
        ON qbank_questions(qbank_topic_id);
    """)

    # ── Year + type columns (NEW) ───────────────────────────────
    cur.execute("""
        ALTER TABLE qbank_questions
            ADD COLUMN IF NOT EXISTS exam_year INTEGER,
            ADD COLUMN IF NOT EXISTS exam_type VARCHAR(20)
                CHECK (exam_type IN ('regular', 'supplementary'));
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_qbank_questions_year_type
            ON qbank_questions(exam_year, exam_type)
            WHERE exam_year IS NOT NULL;
    """)
    print("[database] qbank_questions table ready (with year columns)")
    # ═══════════════════════════════════════════════════════════════
    # QBANK_SECTION_COMPLETION
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS qbank_section_completion (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            qbank_topic_id INTEGER NOT NULL REFERENCES qbank_topics(id) ON DELETE CASCADE,
            category_id INTEGER NOT NULL REFERENCES question_categories(id) ON DELETE CASCADE,
            completed_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, qbank_topic_id, category_id)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_section_completion_user
        ON qbank_section_completion(user_id, qbank_topic_id);
    """)
    print("[database] qbank_section_completion table ready")

    # ═══════════════════════════════════════════════════════════════
    # 20. USER_QBANK_NOTES
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_qbank_notes (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            qbank_question_id INTEGER NOT NULL REFERENCES qbank_questions(id) ON DELETE CASCADE,
            notes TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, qbank_question_id)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_qbank_notes_user
        ON user_qbank_notes(user_id);
    """)
    
        # ═══════════════════════════════════════════════════════════════
    # 21. USER_QBANK_BOOKMARKS
    # ═══════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_qbank_bookmarks (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            qbank_question_id INTEGER NOT NULL REFERENCES qbank_questions(id) ON DELETE CASCADE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, qbank_question_id)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_qbank_bookmarks_user
        ON user_qbank_bookmarks(user_id);
    """)

# qbank_year_helpers.py
#
# Shared year-paper logic used by both qbank.py (HTML) and api_qbank.py (JSON).






    print("[database] user_qbank_bookmarks table ready")




    print("[database] user_qbank_notes table ready")














    # ═══════════════════════════════════════════════════════════════
    # Commit everything
    # ═══════════════════════════════════════════════════════════════
    conn.commit()
    cur.close()
    conn.close()
    print()
    print("[database] All 16 tables ready.")


if __name__ == "__main__":
    init_db()