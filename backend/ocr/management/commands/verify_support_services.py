"""Verify Redis broker, Celery worker, and MinIO object store (TEST support tier)."""

from __future__ import annotations

import uuid
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Verify Redis Celery broker, optional worker ping task, and "
        "MinIO (or FS) upload/download for OCR storage."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-celery-worker",
            action="store_true",
            help="Only check broker + object store (no worker round-trip).",
        )
        parser.add_argument(
            "--celery-timeout",
            type=float,
            default=15.0,
            help="Seconds to wait for sufler.ping task result.",
        )

    def handle(self, *args, **options):
        self._check_redis_broker()
        if not options["skip_celery_worker"]:
            self._check_celery_worker(timeout=options["celery_timeout"])
        else:
            self.stdout.write(
                self.style.WARNING("celery worker: skipped (--skip-celery-worker)")
            )
        self._check_object_store()
        self.stdout.write(self.style.SUCCESS("verify_support_services: OK"))

    def _check_redis_broker(self) -> None:
        broker = getattr(settings, "CELERY_BROKER_URL", "") or ""
        if not broker.startswith(("redis://", "rediss://")):
            raise CommandError(
                f"CELERY_BROKER_URL is not Redis: {broker!r}"
            )
        try:
            import redis
        except ImportError as exc:
            raise CommandError("redis package missing") from exc

        client = redis.Redis.from_url(
            broker,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        if client.ping() is not True:
            raise CommandError(f"Redis broker ping failed: {broker}")
        parsed = urlparse(broker)
        self.stdout.write(
            self.style.SUCCESS(
                f"redis broker: ok ({parsed.hostname}:{parsed.port or 6379})"
            )
        )

    def _check_celery_worker(self, *, timeout: float) -> None:
        from sufler.celery import ping

        try:
            async_result = ping.delay()
            value = async_result.get(timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(
                "Celery worker did not answer sufler.ping — "
                f"is celery-worker running? ({exc})"
            ) from exc
        if value != "pong":
            raise CommandError(f"unexpected ping result: {value!r}")
        self.stdout.write(
            self.style.SUCCESS("celery worker: ok (sufler.ping → pong)")
        )

    def _check_object_store(self) -> None:
        from ocr.storage import ObjectStoreError, get_object_store

        store = get_object_store()
        key = f"support-probe/{uuid.uuid4().hex}.txt"
        payload = b"sufler-support-tier-probe\n"
        try:
            uri = store.put_bytes(
                key,
                payload,
                content_type="text/plain",
            )
            if not store.exists(key):
                raise CommandError(f"object missing after put: {key}")
            got = store.get_bytes(key)
        except ObjectStoreError as exc:
            raise CommandError(f"object store failure: {exc}") from exc

        if got != payload:
            raise CommandError("upload/download mismatch")

        backend = type(store).__name__
        bucket = getattr(settings, "MINIO_OCR_BUCKET", "sufler-ocr")
        self.stdout.write(
            self.style.SUCCESS(
                f"object store: ok ({backend}, bucket={bucket}, uri={uri})"
            )
        )
