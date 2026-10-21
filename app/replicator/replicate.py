"""
app/replicator/replicate.py
Cross-cloud database & object-storage replicator.
Runs on the AWS VM. Every INTERVAL_SECONDS it:
  1. Reads rows changed since watermark from RDS (SOURCE)
  2. Upserts them into Azure PostgreSQL (TARGET)
  3. Syncs S3 bucket → Azure Blob via rclone
"""
import os
import time
import subprocess
import logging

try:
    import psycopg
    PSYCOPG_OK = True
except ImportError:
    PSYCOPG_OK = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [replicator] %(message)s")
log = logging.getLogger("replicator")

SRC_URL = os.environ.get("SOURCE_DATABASE_URL", "")
DST_URL = os.environ.get("TARGET_DATABASE_URL", "")
INTERVAL = int(os.getenv("INTERVAL_SECONDS", "10"))
S3_BUCKET = os.getenv("STORAGE_BUCKET", "fld-screen-images")
AZURE_CONTAINER = os.getenv("AZURE_BLOB_CONTAINER", "images")

UPSERT_SQL = """
INSERT INTO predictions (id, created_at, updated_at, image_key, label, probs, features)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
  updated_at = EXCLUDED.updated_at,
  label      = EXCLUDED.label,
  probs      = EXCLUDED.probs,
  features   = EXCLUDED.features
"""

SELECT_SQL = """
SELECT id, created_at, updated_at, image_key, label, probs, features
FROM predictions
WHERE updated_at > %s
ORDER BY updated_at
"""


def get_watermark(dst_conn):
    row = dst_conn.execute(
        "SELECT COALESCE(MAX(updated_at), '1970-01-01'::timestamptz) FROM predictions"
    ).fetchone()
    return row[0]


def run_rclone_sync():
    cmd = [
        "rclone", "sync",
        f"s3:{S3_BUCKET}",
        f"azblob:{AZURE_CONTAINER}",
        "--fast-list",
        "--transfers=4",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        log.warning(f"rclone sync non-zero exit: {result.stderr[:200]}")
    else:
        log.info("rclone sync OK")


def main():
    if not PSYCOPG_OK:
        log.error("psycopg not installed – replicator cannot run.")
        return
    if not SRC_URL or not DST_URL:
        log.error("SOURCE_DATABASE_URL or TARGET_DATABASE_URL not set.")
        return

    log.info(f"Replicator starting. interval={INTERVAL}s")

    with psycopg.connect(SRC_URL) as src, psycopg.connect(DST_URL) as dst:
        while True:
            try:
                wm = get_watermark(dst)
                rows = src.execute(SELECT_SQL, (wm,)).fetchall()
                if rows:
                    dst.executemany(UPSERT_SQL, rows)
                    dst.commit()
                    log.info(f"Replicated {len(rows)} row(s), new watermark ≈ {rows[-1][2]}")
                else:
                    log.debug(f"No new rows since {wm}")
                run_rclone_sync()
            except Exception as exc:
                log.error(f"Replication cycle error: {exc}")
            time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
