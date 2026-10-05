from django.apps import AppConfig


class QuConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "qu"
    verbose_name = "Query Understanding"

    def ready(self) -> None:
        # Register the reindex.completed receiver for every Django process.
        from qu import tasks  # noqa: F401
