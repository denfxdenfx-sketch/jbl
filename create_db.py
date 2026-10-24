"""
Database connection helper.
Reads DATABASE_URL from environment, or falls back to a local .env file.
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor


def _load_dotenv_if_present():
    """Minimal .env loader (no external dependency)."""
    if os.path.isfile(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                os.environ.setdefault(k, v)


_load_dotenv_if_present()


def get_database_url() -> str:
    """Return the Postgres URL. Raises if not set."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set.\n"
            "  On Render: add it in Environment → Environment Variables\n"
            "  On Mac:    create a .env file with DATABASE_URL=postgres://..."
        )
    # Railway / Heroku sometimes give postgres:// but psycopg2 wants postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def get_connection():
    """Open a new Postgres connection."""
    return psycopg2.connect(get_database_url())


__all__ = ["get_connection", "get_database_url"]
