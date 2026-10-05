"""Start a vendor-shaped pickup without their PBX (local glue check)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from integrations.oktell.call_hub import hub
from integrations.oktell.webhook import parse_pickup_payload


class Command(BaseCommand):
    help = "POST-equivalent: start dual-leg mock listeners and push text into /ws/sufler/<Idchain>/"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--caller", default="375336664177")
        parser.add_argument("--called", default="1001")
        parser.add_argument("--idchain", default="test-chain-1")
        parser.add_argument("--op-name", default="operator1")
        parser.add_argument("--call-type", default="in")

    def handle(self, *args, **options) -> None:
        pickup = parse_pickup_payload(
            {
                "CallerID": options["caller"],
                "CalledID": options["called"],
                "Idchain": options["idchain"],
                "op_name": options["op_name"],
                "call_type": options["call_type"],
            }
        )
        call, created = hub.start(pickup)
        self.stdout.write(
            self.style.SUCCESS(
                f"{'created' if created else 'existing'} {call.idchain} "
                f"legs={[leg.dial for leg in call.legs]}"
            )
        )
        self.stdout.write(f"Open /sufler?callId={call.idchain}")
