"""Long-poll Telegram updates (test contour; no HTTPS webhook / ngrok)."""

from __future__ import annotations

import time

from django.conf import settings
from django.core.management.base import BaseCommand

from online_chat.telegram_polling import run_polling_loop


class Command(BaseCommand):
    help = (
        "Long-poll Telegram getUpdates and route them like the webhook. "
        "Clears setWebhook on start. Use for local/test without ngrok."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeout",
            type=int,
            default=None,
            help="Telegram long-poll timeout seconds (default: TELEGRAM_POLL_TIMEOUT_SECONDS).",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Exit if token/mode not ready (do not idle-wait).",
        )

    def handle(self, *args, **options):
        while True:
            token = (getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "").strip()
            mode = (getattr(settings, "TELEGRAM_MODE", "polling") or "polling").strip().lower()
            if token and mode in {"polling", "both"}:
                break
            msg = (
                f"Telegram polling idle (token={'set' if token else 'empty'}, "
                f"TELEGRAM_MODE={mode!r}); waiting for polling+token"
            )
            self.stdout.write(self.style.WARNING(msg))
            if options["once"]:
                return
            time.sleep(30)

        self.stdout.write(
            self.style.SUCCESS(
                f"Telegram polling started (mode={mode}). Ctrl+C to stop."
            )
        )
        run_polling_loop(timeout_seconds=options["timeout"])
