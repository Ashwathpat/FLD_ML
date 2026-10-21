"""
app/db.py
PostgreSQL database adapter using psycopg v3.
Schema: predictions table (UUID PK, timestamps, image_key, label, probs JSONB, features JSONB).
"""
import os
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

try:
    import psycopg
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False

DATABASE_URL = os.getenv("DATABASE_URL", "")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS predictions (
    id          UUID PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    image_key   TEXT NOT NULL,
    label       TEXT NOT NULL,
    probs       JSONB NOT NULL,
    features    JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_predictions_updated ON predictions (updated_at);
"""


def get_connection():
    """Returns a psycopg connection, or None if DB is unavailable."""
    if not PSYCOPG_AVAILABLE or not DATABASE_URL:
        return None
    try:
        return psycopg.connect(DATABASE_URL)
    except Exception as e:
        print(f"[db.py] DB connection failed: {e}")
        return None


def init_db() -> bool:
    """Creates predictions table if it doesn't exist. Returns True on success."""
    conn = get_connection()
    if conn is None:
        print("[db.py] Skipping DB init – no connection.")
        return False
    try:
        with conn:
            conn.execute(CREATE_TABLE_SQL)
        print("[db.py] DB schema initialised.")
        return True
    except Exception as e:
        print(f"[db.py] DB init error: {e}")
        return False
    finally:
        conn.close()


def save_prediction(
    image_key: str,
    label: str,
    probs: dict,
    features: dict,
    pred_id: Optional[str] = None,
) -> str:
    """
    Inserts a prediction record. Returns the UUID string.
    Silently skips on DB unavailability so the API remains functional.
    """
    if pred_id is None:
        pred_id = str(uuid.uuid4())
    conn = get_connection()
    if conn is None:
        return pred_id
    now = datetime.now(timezone.utc)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO predictions (id, created_at, updated_at, image_key, label, probs, features)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (pred_id, now, now, image_key, label,
                 json.dumps(probs), json.dumps(features)),
            )
    except Exception as e:
        print(f"[db.py] save_prediction error: {e}")
    finally:
        conn.close()
    return pred_id


def db_reachable() -> bool:
    """Health check: returns True if DB is reachable."""
    conn = get_connection()
    if conn is None:
        return False
    try:
        conn.execute("SELECT 1")
        return True
    except Exception:
        return False
    finally:
        conn.close()
