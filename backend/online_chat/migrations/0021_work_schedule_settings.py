import datetime

from django.db import migrations, models

import online_chat.models


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0020_dialog_client_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkScheduleSettings",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "enabled",
                    models.BooleanField(
                        default=False,
                        help_text="Учитывать рабочее время: вне графика диалоги не распределяются",
                    ),
                ),
                ("start_time", models.TimeField(default=datetime.time(9, 0))),
                ("end_time", models.TimeField(default=datetime.time(18, 0))),
                (
                    "workdays",
                    models.JSONField(
                        blank=True, default=online_chat.models.default_workdays
                    ),
                ),
                ("holidays", models.JSONField(blank=True, default=list)),
                (
                    "manual_override",
                    models.CharField(
                        choices=[
                            ("auto", "По расписанию"),
                            ("open", "Рабочий день начат"),
                            ("closed", "Нерабочее время"),
                        ],
                        default="auto",
                        help_text="Ручное переопределение расписания (демо / форс-мажор)",
                        max_length=8,
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Work schedule settings",
                "verbose_name_plural": "Work schedule settings",
            },
        ),
    ]
