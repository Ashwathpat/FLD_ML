"""
app/storage.py
Object-storage adapter.
Routes to AWS S3 or Azure Blob based on CLOUD_NAME env var.
Falls back to local filesystem if neither cloud SDK is configured.
"""
import os
import uuid
from pathlib import Path
from typing import BinaryIO

CLOUD_NAME = os.getenv("CLOUD_NAME", "local").lower()
STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "fld-screen-images")
LOCAL_STORAGE_DIR = Path("ml/data/uploads")


def _save_local(key: str, data: bytes) -> str:
    LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCAL_STORAGE_DIR / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return str(path)


def upload_image(file_bytes: bytes, filename: str = None) -> str:
    """
    Uploads image bytes to the configured storage backend.

    Returns:
        object_key (str): Unique storage key for the uploaded object.
    """
    suffix = Path(filename).suffix if filename else ".jpg"
    key = f"tongues/{uuid.uuid4().hex}{suffix}"

    if CLOUD_NAME == "aws":
        return _upload_s3(key, file_bytes)
    elif CLOUD_NAME == "azure":
        return _upload_blob(key, file_bytes)
    else:
        return _save_local(key, file_bytes)


def _upload_s3(key: str, data: bytes) -> str:
    try:
        import boto3
        s3 = boto3.client("s3")
        s3.put_object(Bucket=STORAGE_BUCKET, Key=key, Body=data)
        return key
    except Exception as e:
        print(f"[storage.py] S3 upload failed, falling back to local: {e}")
        return _save_local(key, data)


def _upload_blob(key: str, data: bytes) -> str:
    try:
        from azure.storage.blob import BlobServiceClient
        conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        client = BlobServiceClient.from_connection_string(conn_str)
        blob = client.get_blob_client(container=STORAGE_BUCKET, blob=key)
        blob.upload_blob(data, overwrite=True)
        return key
    except Exception as e:
        print(f"[storage.py] Azure Blob upload failed, falling back to local: {e}")
        return _save_local(key, data)
