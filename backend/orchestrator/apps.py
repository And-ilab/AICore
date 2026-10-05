import os
import sys
import threading

from django.apps import AppConfig


class OrchestratorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "orchestrator"

    def ready(self) -> None:
        joined = " ".join(sys.argv).lower()
        if "pytest" in joined or os.environ.get("PYTEST_CURRENT_TEST"):
            return
        if any(
            arg in {"migrate", "makemigrations", "collectstatic", "test", "shell"}
            for arg in sys.argv[1:2]
        ):
            return

        def _warm() -> None:
            from orchestrator.scenario_engine import warm_scenario_semantics

            warm_scenario_semantics()

        threading.Thread(target=_warm, name="scenario-semantic-ready", daemon=True).start()
