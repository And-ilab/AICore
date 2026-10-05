# Generated manually for SuzReconcileState (INT-09).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ingest", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SuzReconcileState",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "cursor",
                    models.CharField(
                        default="1970-01-01T00:00:00+00:00",
                        max_length=64,
                    ),
                ),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
                ("last_accepted", models.PositiveIntegerField(default=0)),
                ("last_skipped", models.PositiveIntegerField(default=0)),
                ("last_failed", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "SUZ reconcile state",
                "verbose_name_plural": "SUZ reconcile state",
            },
        ),
    ]
