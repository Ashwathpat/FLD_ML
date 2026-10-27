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
        region = os.getenv("AWS_DEFAULT_REGION", "ap-southeast-2")
        s3 = boto3.client("s3", region_name=region)
        s3.put_object(Bucket=STORAGE_BUCKET, Key=key, Body=data)
        return key
    except Exception as e:
        print(f"[storage.py] S3 upload failed, falling back to local: {e}")
        return _save_local(key, data)


def _upload_blob(key: str, data: bytes) -> str:
    try:
        from azure.storage.blob import BlobServiceClient
        conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        if conn_str:
            client = BlobServiceClient.from_connection_string(conn_str)
        else:
            account_name = os.getenv("AZURE_STORAGE_ACCOUNT", "")
            account_key = os.getenv("AZURE_STORAGE_KEY", "")
            account_url = f"https://{account_name}.blob.core.windows.net"
            client = BlobServiceClient(account_url=account_url, credential=account_key)
        blob = client.get_blob_client(container=STORAGE_BUCKET, blob=key)
        blob.upload_blob(data, overwrite=True)
        return key
    except Exception as e:
        print(f"[storage.py] Azure Blob upload failed, falling back to local: {e}")
        return _save_local(key, data)


def get_image(key: str) -> bytes:
    """Retrieves image bytes from AWS S3, Azure Blob, or local fallback."""
    if CLOUD_NAME == "aws":
        try:
            import boto3
            region = os.getenv("AWS_DEFAULT_REGION", "ap-southeast-2")
            s3 = boto3.client("s3", region_name=region)
            resp = s3.get_object(Bucket=STORAGE_BUCKET, Key=key)
            return resp["Body"].read()
        except Exception as e:
            print(f"[storage.py] S3 read error: {e}")
    elif CLOUD_NAME == "azure":
        try:
            from azure.storage.blob import BlobServiceClient
            conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
            if conn_str:
                client = BlobServiceClient.from_connection_string(conn_str)
            else:
                account_name = os.getenv("AZURE_STORAGE_ACCOUNT", "")
                account_key = os.getenv("AZURE_STORAGE_KEY", "")
                account_url = f"https://{account_name}.blob.core.windows.net"
                client = BlobServiceClient(account_url=account_url, credential=account_key)
            blob = client.get_blob_client(container=STORAGE_BUCKET, blob=key)
            return blob.download_blob().readall()
        except Exception as e:
            print(f"[storage.py] Azure read error: {e}")

    # Fallback to local
    path = LOCAL_STORAGE_DIR / key
    if path.exists():
        return path.read_bytes()
    raise FileNotFoundError(f"Object {key} not found in cloud storage or local storage.")


def delete_image(key: str) -> bool:
    """
    Deletes an image from cloud storage (AWS S3 and/or Azure Blob) and local disk.
    Ensures complete cleanup when a record is deleted.
    """
    success = False
    # 1. AWS S3 deletion
    try:
        import boto3
        region = os.getenv("AWS_DEFAULT_REGION", "ap-southeast-2")
        s3 = boto3.client("s3", region_name=region)
        s3.delete_object(Bucket=STORAGE_BUCKET, Key=key)
        success = True
    except Exception as e:
        print(f"[storage.py] S3 delete error for {key}: {e}")

    # 2. Azure Blob deletion
    try:
        from azure.storage.blob import BlobServiceClient
        conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        if conn_str:
            client = BlobServiceClient.from_connection_string(conn_str)
        else:
            account_name = os.getenv("AZURE_STORAGE_ACCOUNT", "")
            account_key = os.getenv("AZURE_STORAGE_KEY", "")
            if account_name:
                account_url = f"https://{account_name}.blob.core.windows.net"
                client = BlobServiceClient(account_url=account_url, credential=account_key)
            else:
                client = None
        if client:
            blob = client.get_blob_client(container=STORAGE_BUCKET, blob=key)
            blob.delete_blob(delete_snapshots="include")
            success = True
    except Exception as e:
        print(f"[storage.py] Azure Blob delete error for {key}: {e}")

    # 3. Local disk deletion
    path = LOCAL_STORAGE_DIR / key
    if path.exists():
        try:
            path.unlink()
            success = True
        except Exception as e:
            print(f"[storage.py] Local delete error for {key}: {e}")

    return success


def purge_all_images(prefix: str = "tongues/") -> int:
    """
    Purges all uploaded images under prefix from AWS S3, Azure Blob, and local storage.
    Called when 'Clear All History' is triggered.
    """
    deleted_count = 0
    # 1. AWS S3
    try:
        import boto3
        region = os.getenv("AWS_DEFAULT_REGION", "ap-southeast-2")
        s3 = boto3.client("s3", region_name=region)
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=STORAGE_BUCKET, Prefix=prefix):
            objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if objects:
                s3.delete_objects(Bucket=STORAGE_BUCKET, Delete={"Objects": objects})
                deleted_count += len(objects)
    except Exception as e:
        print(f"[storage.py] S3 purge error: {e}")

    # 2. Azure Blob
    try:
        from azure.storage.blob import BlobServiceClient
        conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        if conn_str:
            client = BlobServiceClient.from_connection_string(conn_str)
        else:
            account_name = os.getenv("AZURE_STORAGE_ACCOUNT", "")
            account_key = os.getenv("AZURE_STORAGE_KEY", "")
            if account_name:
                account_url = f"https://{account_name}.blob.core.windows.net"
                client = BlobServiceClient(account_url=account_url, credential=account_key)
            else:
                client = None
        if client:
            container = client.get_container_client(STORAGE_BUCKET)
            for blob in container.list_blobs(name_starts_with=prefix):
                container.delete_blob(blob.name)
    except Exception as e:
        print(f"[storage.py] Azure Blob purge error: {e}")

    # 3. Local disk
    try:
        local_prefix_dir = LOCAL_STORAGE_DIR / prefix
        if local_prefix_dir.exists():
            import shutil
            shutil.rmtree(local_prefix_dir, ignore_errors=True)
    except Exception as e:
        print(f"[storage.py] Local purge error: {e}")

    return deleted_count

