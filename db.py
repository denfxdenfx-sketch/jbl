import os
from urllib.parse import urlparse
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor


def _build_db_config():
    """
    Priority:
      1. DB_* env vars (local dev / custom names)
      2. DATABASE_URL (Railway / Heroku / most PaaS)
      3. localhost defaults (last resort)
    """
    if os.environ.get("DB_HOST"):
        return {
            "host":     os.environ["DB_HOST"],
            "database": os.environ.get("DB_NAME", "myapp_db"),
            "user":     os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", ""),
            "port":     os.environ.get("DB_PORT", "5432"),
        }

    if os.environ.get("DATABASE_URL"):
        url = urlparse(os.environ["DATABASE_URL"])
        return {
            "host":     url.hostname,
            "database": url.path.lstrip("/"),
            "user":     url.username,
            "password": url.password,
            "port":     url.port or 5432,
        }

    # Localhost fallback (dev only)
    return {
        "host":     "localhost",
        "database": "myapp_db",
        "user":     "postgres",
        "password": "br09s3765",
        "port":     "5432",
    }


DB_CONFIG = _build_db_config()


@contextmanager
def db_cursor():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
