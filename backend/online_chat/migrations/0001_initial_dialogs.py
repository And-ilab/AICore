# ruff: noqa: RUF012
import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Dialog",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("widget_id", models.CharField(blank=True, default="", max_length=128)),
                (
                    "placement",
                    models.CharField(blank=True, default="website", max_length=64),
                ),
                ("channel", models.CharField(default="widget", max_length=32)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("waiting", "Ожидает ответа"),
                            ("active", "В диалоге"),
                            ("closed", "Закрыт"),
                            ("blocked", "Заблокирован"),
                        ],
                        db_index=True,
                        default="waiting",
                        max_length=16,
                    ),
                ),
                (
                    "client_first_name",
                    models.CharField(blank=True, default="", max_length=100),
                ),
                (
                    "client_last_name",
                    models.CharField(blank=True, default="", max_length=100),
                ),
                (
                    "client_phone",
                    models.CharField(blank=True, default="", max_length=40),
                ),
                (
                    "operator_name",
                    models.CharField(blank=True, default="", max_length=120),
                ),
                ("preview", models.CharField(blank=True, default="", max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="DialogMessage",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "speaker",
                    models.CharField(
                        choices=[
                            ("client", "Клиент"),
                            ("operator", "Оператор"),
                            ("system", "Система"),
                        ],
                        max_length=16,
                    ),
                ),
                ("text", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "dialog",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to="online_chat.dialog",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="dialog",
            index=models.Index(
                fields=["status", "-updated_at"],
                name="online_chat_status_6f0d0a_idx",
            ),
        ),
    ]
