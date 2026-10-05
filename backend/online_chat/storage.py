from __future__ import annotations

from pathlib import Path

from django.conf import settings

from ocr.storage import FilesystemObjectStore, MinioObjectStore, ObjectStore


def get_chat_object_store() -> ObjectStore:
    backend = getattr(settings, "ONLINE_CHAT_OBJECT_STORE_BACKEND", "auto")
    access = getattr(settings, "MINIO_ACCESS_KEY", "") or ""
    secret = getattr(settings, "MINIO_SECRET_KEY", "") or ""
    bucket = getattr(settings, "MINIO_ONLINE_CHAT_BUCKET", "sufler-online-chat")
    if backend == "fs" or (backend == "auto" and (not access or not secret)):
        root = Path(getattr(settings, "ONLINE_CHAT_OBJECT_STORE_ROOT"))
        return FilesystemObjectStore(root, bucket)
    return MinioObjectStore(
        endpoint=getattr(settings, "MINIO_ENDPOINT", "http://localhost:9000"),
        access_key=access,
        secret_key=secret,
        bucket=bucket,
    )
