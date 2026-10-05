import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("online_chat", "0008_message_attachments"),
    ]

    operations = [
        migrations.CreateModel(
            name="BotConfiguration",
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
                ("name", models.CharField(max_length=160)),
                ("is_active", models.BooleanField(db_index=True, default=False)),
                ("welcome_message", models.TextField(blank=True, default="")),
                (
                    "fallback_message",
                    models.TextField(
                        blank=True,
                        default="Передаю обращение оператору.",
                    ),
                ),
                ("trigger_responses", models.JSONField(blank=True, default=dict)),
                ("max_bot_turns", models.PositiveIntegerField(default=3)),
                (
                    "handoff_message",
                    models.TextField(
                        blank=True,
                        default="Подключаю оператора. Пожалуйста, ожидайте.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "department",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bots",
                        to="online_chat.department",
                    ),
                ),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.AddField(
            model_name="dialog",
            name="bot_active",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="dialog",
            name="bot_turns",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="dialogmessage",
            name="speaker",
            field=models.CharField(
                choices=[
                    ("client", "Клиент"),
                    ("operator", "Оператор"),
                    ("bot", "Бот"),
                    ("system", "Система"),
                ],
                max_length=16,
            ),
        ),
    ]
