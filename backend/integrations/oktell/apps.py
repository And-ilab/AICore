import os
import sys
import threading
import time

from django.apps import AppConfig


class TelephonyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "telephony"

    def ready(self) -> None:
        if os.environ.get("RUN_MAIN") != "true" and "runserver" in sys.argv:
            return
        if any(cmd in sys.argv for cmd in ("migrate", "makemigrations", "collectstatic", "test")):
            return
        worker = threading.Thread(target=_boot_live_listen, name="oktell-boot-live", daemon=True)
        worker.start()


def _boot_live_listen() -> None:
    time.sleep(2)
    from django.conf import settings

    if str(getattr(settings, "OKTELL_LISTEN_MODE", "") or "").strip().lower() != "sip":
        return
    from integrations.oktell.call_hub import hub
    from integrations.oktell.webhook import PickupEvent

    line = str(getattr(settings, "OKTELL_SIP_LISTEN_LINE", "1001") or "1001")
    pickup = PickupEvent(
        caller_id="sufler",
        called_id=line,
        idchain="live",
        op_name="sufler",
        call_type="in",
    )
    try:
        hub.start(pickup)
    except Exception:
        return
