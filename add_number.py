# seed_user.py
from werkzeug.security import generate_password_hash
from db import db_cursor

with db_cursor() as cur:
    cur.execute("""
        INSERT INTO users (username, email, phone_number, password_hash, first_name)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (email) DO NOTHING
    """, (
        "Anshu",
        "anshukumarraaj2005@gmail.com",
        "+918825284277",              # ← your verified phone number, with +
        generate_password_hash("pass123"),
        "Alice",
    ))
    print("User created (or already existed)")