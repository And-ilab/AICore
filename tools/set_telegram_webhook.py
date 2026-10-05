#!/usr/bin/env python3
"""Register Telegram webhook URL (local ngrok → Django).

Usage:
  export TELEGRAM_BOT_TOKEN=...
  python tools/set_telegram_webhook.py https://XXXX.ngrok-free.app

Or:
  cd infra && docker compose exec -e NGROK_URL=https://XXXX.ngrok-free.app backend \\
    python - <<'PY'
  ...
  PY
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request


def main() -> int:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN is empty", file=sys.stderr)
        return 1
    if len(sys.argv) < 2:
        print(
            "Usage: set_telegram_webhook.py https://XXXX.ngrok-free.app",
            file=sys.stderr,
        )
        return 1
    base = sys.argv[1].rstrip("/")
    webhook = f"{base}/api/v1/channels/telegram/webhook/"

    def call(method: str, **params: str) -> dict:
        url = f"https://api.telegram.org/bot{token}/{method}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=20) as response:
            return json.loads(response.read().decode())

    info_before = call("getWebhookInfo")
    print("before:", json.dumps(info_before.get("result", {}), ensure_ascii=False))
    # Drop pending updates so /start is clean.
    result = call("setWebhook", url=webhook, drop_pending_updates="true")
    print("setWebhook:", json.dumps(result, ensure_ascii=False))
    me = call("getMe")
    print("bot:", json.dumps(me.get("result", {}), ensure_ascii=False))
    info_after = call("getWebhookInfo")
    print("after:", json.dumps(info_after.get("result", {}), ensure_ascii=False))
    if not result.get("ok"):
        return 2
    print("OK — write /start to the bot above")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
