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


def get_connection(db_url: Optional[str] = None):
    """Returns a psycopg connection, or None if DB is unavailable, with automatic cloud fallback."""
    if not PSYCOPG_AVAILABLE:
        return None
    candidate_urls = []
    if db_url:
        candidate_urls.append(db_url)
    elif DATABASE_URL:
        candidate_urls.append(DATABASE_URL)
    for u in get_all_db_urls():
        if u not in candidate_urls:
            candidate_urls.append(u)

    for url in candidate_urls:
        try:
            return psycopg.connect(url, connect_timeout=2.5)
        except Exception:
            continue
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


def get_recent_predictions(limit: int = 15):
    """Fetches recent prediction records with timestamps, keys, and labels."""
    conn = get_connection()
    if conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, created_at, image_key, label, probs, features
                FROM predictions
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,)
            )
            rows = cur.fetchall()
            results = []
            for r in rows:
                results.append({
                    "id": str(r[0]),
                    "created_at": r[1].isoformat() if r[1] else "",
                    "image_key": r[2],
                    "label": r[3],
                    "probs": r[4] if isinstance(r[4], dict) else json.loads(r[4]) if r[4] else {},
                    "features": r[5] if isinstance(r[5], dict) else json.loads(r[5]) if r[5] else {},
                })
            return results
    except Exception as e:
        print(f"[db.py] get_recent_predictions error: {e}")
        return []
    finally:
        conn.close()


def get_all_db_urls() -> list:
    """Returns all available cloud database URLs (AWS RDS + Azure PG)."""
    urls = []
    aws_rds = "postgresql://fld_user:FldSecurePass2026!@fld-pg.cj4y80kwm16d.ap-southeast-2.rds.amazonaws.com:5432/fld_db"
    azure_pg = "postgresql://fld_user:FldSecurePass2026!@fld-pg-standby-fld01.postgres.database.azure.com:5432/fld_db?sslmode=require"
    
    for var in ["DATABASE_URL", "TARGET_DATABASE_URL", "SOURCE_DATABASE_URL"]:
        val = os.getenv(var)
        if val and val not in urls and "localhost" not in val and "127.0.0.1" not in val:
            urls.append(val)
            
    if aws_rds not in urls:
        urls.append(aws_rds)
    if azure_pg not in urls:
        urls.append(azure_pg)
    return urls


def delete_prediction(pred_id: str) -> dict:
    """Deletes a prediction record by UUID across BOTH AWS and Azure databases."""
    deleted_from = []
    errors = []
    row_found = False
    for url in get_all_db_urls():
        try:
            with psycopg.connect(url, connect_timeout=2.5) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM predictions WHERE id = %s", (pred_id,))
                    if cur.rowcount > 0:
                        row_found = True
                conn.commit()
                host = url.split("@")[-1].split("/")[0]
                deleted_from.append(host)
        except Exception as e:
            errors.append(f"{url.split('@')[-1].split('/')[0]}: {e}")
    return {"deleted_id": pred_id, "found": row_found, "targets": deleted_from, "errors": errors}


def clear_all_predictions() -> dict:
    """Deletes ALL records across BOTH AWS and Azure databases using DELETE to ensure compatibility."""
    cleared_from = []
    errors = []
    total_deleted = 0
    for url in get_all_db_urls():
        try:
            with psycopg.connect(url, connect_timeout=2.5) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM predictions")
                    count = cur.rowcount
                    if count >= 0:
                        total_deleted += count
                conn.commit()
                host = url.split("@")[-1].split("/")[0]
                cleared_from.append(f"{host} ({count} rows)")
        except Exception as e:
            errors.append(f"{url.split('@')[-1].split('/')[0]}: {e}")
    return {"status": "all_cleared", "deleted_rows": total_deleted, "targets": cleared_from, "errors": errors}

