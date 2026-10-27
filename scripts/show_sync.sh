#!/bin/bash
echo "================================================================="
echo "   FLD-SCREEN: MULTI-CLOUD LIVE REPLICATION & STORAGE AUDIT"
echo "================================================================="
echo ""
echo "--- [1] DATABASE COMPARISON (AWS RDS vs Azure PostgreSQL) ---"
sudo docker exec fld-app-1 python -c '
import psycopg, os
aws_db = os.getenv("DATABASE_URL")
az_db = os.getenv("TARGET_DATABASE_URL")

with psycopg.connect(aws_db) as c:
    cur = c.cursor()
    cur.execute("SELECT count(*) FROM predictions")
    aws_cnt = cur.fetchone()[0]
    cur.execute("SELECT id, created_at, image_key, label FROM predictions ORDER BY created_at DESC LIMIT 3")
    aws_rows = cur.fetchall()

with psycopg.connect(az_db) as c:
    cur = c.cursor()
    cur.execute("SELECT count(*) FROM predictions")
    az_cnt = cur.fetchone()[0]
    cur.execute("SELECT id, created_at, image_key, label FROM predictions ORDER BY created_at DESC LIMIT 3")
    az_rows = cur.fetchall()

print(f"  * AWS RDS Total Records       : {aws_cnt}")
for r in aws_rows:
    ts = r[1].strftime("%H:%M:%S")
    id_prefix = str(r[0])[:8]
    print(f"    - [{ts} UTC] ID: {id_prefix}... | Key: {r[2]} | Result: {r[3]}")

print(f"\n  * Azure Standby Total Records : {az_cnt}")
for r in az_rows:
    ts = r[1].strftime("%H:%M:%S")
    id_prefix = str(r[0])[:8]
    print(f"    - [{ts} UTC] ID: {id_prefix}... | Key: {r[2]} | Result: {r[3]}")

if aws_cnt == az_cnt:
    print(f"\n  >>> STATUS: BOTH DATABASES 100% IN SYNC ({aws_cnt} records) <<<")
else:
    print(f"\n  >>> STATUS: Replicator in progress ({aws_cnt - az_cnt} row(s) pending) <<<")
'

echo ""
echo "--- [2] OBJECT STORAGE COMPARISON (AWS S3 vs Azure Blob) ---"
echo "  * AWS S3 (Bucket: fld-screen-images-fld01):"
sudo docker exec fld-replicator-1 rclone lsf s3:fld-screen-images-fld01/tongues/ | sed "s/^/    - s3:\/\/fld-screen-images-fld01\/tongues\//"
echo ""
echo "  * Azure Blob (Account: fldscreenfld01, Container: images):"
sudo docker exec fld-replicator-1 rclone lsf azblob:images/tongues/ | sed "s/^/    - az:\/\/images\/tongues\//"

echo ""
echo "--- [3] LATEST REPLICATOR ACTIVITY LOGS ---"
sudo docker logs --tail 3 fld-replicator-1
echo "================================================================="
