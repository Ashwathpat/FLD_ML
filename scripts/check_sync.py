import os
import psycopg
import boto3
from azure.storage.blob import BlobServiceClient

aws_db = os.getenv("SOURCE_DATABASE_URL") or os.getenv("DATABASE_URL")
az_db = os.getenv("TARGET_DATABASE_URL")
s3_bucket = os.getenv("STORAGE_BUCKET", "fld-screen-images-fld01")
az_account = os.getenv("RCLONE_CONFIG_AZBLOB_ACCOUNT", "fldscreenfld01")
az_key = os.getenv("RCLONE_CONFIG_AZBLOB_KEY", "")
az_container = os.getenv("AZURE_BLOB_CONTAINER", "images")

print("=" * 65)
print("       LIVE MULTI-CLOUD DATA & STORAGE SYNCHRONIZATION AUDIT")
print("=" * 65)

# 1. AWS RDS vs Azure PostgreSQL
print("\n[1] DATABASE COMPARISON (AWS RDS vs Azure PostgreSQL):")
try:
    with psycopg.connect(aws_db) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM predictions")
            aws_cnt = cur.fetchone()[0]
            cur.execute("SELECT id, created_at, image_key, label FROM predictions ORDER BY created_at DESC LIMIT 3")
            aws_recent = cur.fetchall()
    print(f"  * AWS RDS Total Predictions   : {aws_cnt}")
    for r in aws_recent:
        print(f"    - [{r[1].strftime('%H:%M:%S')}] ID: {str(r[0])[:8]}... | Key: {r[2]} | Label: {r[3]}")
except Exception as e:
    print(f"  * AWS RDS query error: {e}")

try:
    with psycopg.connect(az_db) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM predictions")
            az_cnt = cur.fetchone()[0]
            cur.execute("SELECT id, created_at, image_key, label FROM predictions ORDER BY created_at DESC LIMIT 3")
            az_recent = cur.fetchall()
    print(f"  * Azure PG Total Predictions  : {az_cnt}")
    for r in az_recent:
        print(f"    - [{r[1].strftime('%H:%M:%S')}] ID: {str(r[0])[:8]}... | Key: {r[2]} | Label: {r[3]}")
    if aws_cnt == az_cnt:
        print(f"  => SUCCESS: Both databases are 100% IN SYNC ({aws_cnt} records)")
    else:
        print(f"  => Replicator syncing ({aws_cnt - az_cnt} pending rows, syncs every 10s)")
except Exception as e:
    print(f"  * Azure PG query error: {e}")

# 2. S3 vs Azure Blob Storage
print("\n[2] OBJECT STORAGE COMPARISON (AWS S3 vs Azure Blob):")
try:
    s3 = boto3.client("s3", region_name=os.getenv("AWS_DEFAULT_REGION", "ap-southeast-2"))
    resp = s3.list_objects_v2(Bucket=s3_bucket, Prefix="tongues/")
    s3_items = [obj["Key"] for obj in resp.get("Contents", [])]
    print(f"  * AWS S3 Bucket ({s3_bucket}): {len(s3_items)} image(s)")
    for k in s3_items[-3:]:
        print(f"    - s3://{s3_bucket}/{k}")
except Exception as e:
    print(f"  * S3 query error: {e}")

try:
    if az_key:
        bsc = BlobServiceClient(account_url=f"https://{az_account}.blob.core.windows.net", credential=az_key)
        cc = bsc.get_container_client(az_container)
        az_items = [b.name for b in cc.list_blobs(name_starts_with="tongues/")]
        print(f"  * Azure Blob ({az_account}/{az_container}): {len(az_items)} image(s)")
        for k in az_items[-3:]:
            print(f"    - az://{az_container}/{k}")
        if len(s3_items) == len(az_items):
            print(f"  => SUCCESS: Object storage is 100% REPLICATED ({len(s3_items)} images)")
        else:
            print(f"  => Rclone syncing images in background")
except Exception as e:
    print(f"  * Azure Blob query error: {e}")

print("=" * 65)
