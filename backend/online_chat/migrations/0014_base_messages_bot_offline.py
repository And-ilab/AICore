from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0013_dialog_summaries"),
    ]

    operations = [
        migrations.AddField(
            model_name="botconfiguration",
            name="offline_message",
            field=models.TextField(
                blank=True,
                default="Сейчас операторы недоступны. Оставьте сообщение.",
            ),
        ),
        migrations.AlterField(
            model_name="botconfiguration",
            name="department",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="bots",
                to="online_chat.department",
            ),
        ),
        migrations.CreateModel(
            name="BaseMessage",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "message_type",
                    models.CharField(
                        choices=[
                            ("welcome", "Приветствие"),
                            ("offline", "Вне графика"),
                            ("broadcast", "Оповещение"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("title", models.CharField(blank=True, default="", max_length=160)),
                ("text", models.TextField()),
                ("channel", models.CharField(blank=True, default="", max_length=32)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "placement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="base_messages",
                        to="online_chat.widgetplacement",
                    ),
                ),
            ],
            options={
                "ordering": ("message_type", "title", "created_at"),
            },
        ),
    ]
