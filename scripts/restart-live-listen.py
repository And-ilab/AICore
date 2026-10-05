import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")
import django

django.setup()

from integrations.oktell.call_hub import hub
from integrations.oktell.webhook import PickupEvent

hub.stop("live")
call, created = hub.start(
    PickupEvent(
        caller_id="sufler",
        called_id="1001",
        idchain="live",
        op_name="sufler",
        call_type="in",
    )
)
print(
    created,
    call.state,
    [(leg.speaker, leg.status, leg.dial) for leg in call.legs],
)
