import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

app = Celery("sufler")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(name="sufler.ping")
def ping() -> str:
    """Lightweight broker→worker round-trip for TEST support-tier checks."""
    return "pong"
