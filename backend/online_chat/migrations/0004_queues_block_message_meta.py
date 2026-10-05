# Generated manually for online-chat MVP extensions.

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0003_message_receipt_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="dialog",
            name="initiated_by",
            field=models.CharField(
                choices=[("client", "Клиент"), ("operator", "Оператор")],
                db_index=True,
                default="client",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="dialog",
            name="client_online",
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.AddField(
            model_name="dialog",
            name="client_last_seen_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="dialogmessage",
            name="reply_to",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="replies",
                to="online_chat.dialogmessage",
            ),
        ),
        migrations.AddField(
            model_name="dialogmessage",
            name="quoted_text",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="dialogmessage",
            name="edited_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="dialogmessage",
            name="is_deleted",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="dialogmessage",
            name="attachment_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.CreateModel(
            name="ClientBlock",
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
                ("phone", models.CharField(blank=True, default="", max_length=40)),
                ("phone_normalized", models.CharField(db_index=True, max_length=40)),
                ("reason", models.CharField(blank=True, default="", max_length=255)),
                ("blocked_by", models.CharField(blank=True, default="", max_length=120)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("lifted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "dialog",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="client_blocks",
                        to="online_chat.dialog",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
    ]
