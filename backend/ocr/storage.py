"""Object storage for OCR originals and results (MinIO or local FS)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from django.conf import settings


class ObjectStoreError(RuntimeError):
    """Object storage failure."""


class ObjectStore(Protocol):
    def put_bytes(
        self,
        key: str,
        payload: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> str: ...

    def get_bytes(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...


class FilesystemObjectStore:
    """Local filesystem stand-in for MinIO (tests / offline)."""

    def __init__(self, root: Path, bucket: str) -> None:
        self.root = Path(root) / bucket
        self.root.mkdir(parents=True, exist_ok=True)
        self.bucket = bucket

    def _path(self, key: str) -> Path:
        safe = key.lstrip("/").replace("..", "_")
        path = self.root / safe
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def put_bytes(
        self,
        key: str,
        payload: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> str:
        path = self._path(key)
        path.write_bytes(payload)
        meta = path.with_suffix(path.suffix + ".content-type")
        meta.write_text(content_type, encoding="utf-8")
        return f"fs://{self.bucket}/{key}"

    def get_bytes(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise ObjectStoreError(f"Object not found: {key}")
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


class MinioObjectStore:
    """S3-compatible MinIO client."""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
    ) -> None:
        try:
            from minio import Minio
        except ImportError as exc:
            raise ObjectStoreError(
                "minio package is required for MinIO backend"
            ) from exc

        parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
        host = parsed.netloc or parsed.path
        secure = parsed.scheme == "https"
        self._client = Minio(
            host,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self.bucket = bucket
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)

    def put_bytes(
        self,
        key: str,
        payload: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> str:
        from io import BytesIO

        from minio.error import S3Error

        try:
            self._client.put_object(
                self.bucket,
                key,
                BytesIO(payload),
                length=len(payload),
                content_type=content_type,
            )
        except S3Error as exc:
            raise ObjectStoreError(str(exc)) from exc
        return f"s3://{self.bucket}/{key}"

    def get_bytes(self, key: str) -> bytes:
        from minio.error import S3Error

        try:
            response = self._client.get_object(self.bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except S3Error as exc:
            raise ObjectStoreError(str(exc)) from exc

    def exists(self, key: str) -> bool:
        from minio.error import S3Error

        try:
            self._client.stat_object(self.bucket, key)
            return True
        except S3Error:
            return False


def get_object_store() -> ObjectStore:
    backend = getattr(settings, "OCR_OBJECT_STORE_BACKEND", "auto")
    bucket = getattr(settings, "MINIO_OCR_BUCKET", "sufler-ocr")
    access = getattr(settings, "MINIO_ACCESS_KEY", "") or ""
    secret = getattr(settings, "MINIO_SECRET_KEY", "") or ""

    use_fs = backend == "fs" or (
        backend == "auto" and (not access or not secret)
    )
    if use_fs:
        root = Path(getattr(settings, "OCR_OBJECT_STORE_ROOT"))
        return FilesystemObjectStore(root, bucket)

    return MinioObjectStore(
        endpoint=getattr(settings, "MINIO_ENDPOINT", "http://localhost:9000"),
        access_key=access,
        secret_key=secret,
        bucket=bucket,
    )
