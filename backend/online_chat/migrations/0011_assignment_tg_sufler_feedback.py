import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("online_chat", "0010_sufler_response_audit"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssignmentSettings",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "mode",
                    models.CharField(
                        choices=[
                            ("strict_auto", "Только автоназначение"),
                            ("manual_plus_auto", "Ручной выбор + авто (5 сек)"),
                        ],
                        default="manual_plus_auto",
                        max_length=32,
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Assignment settings",
                "verbose_name_plural": "Assignment settings",
            },
        ),
        migrations.CreateModel(
            name="OperatorAssignmentHold",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("until", models.DateTimeField(db_index=True)),
                (
                    "reason",
                    models.CharField(blank=True, default="post_close_grace", max_length=64),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "operator",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assignment_holds",
                        to="online_chat.operatorprofile",
                    ),
                ),
            ],
            options={
                "ordering": ("-until",),
            },
        ),
        migrations.CreateModel(
            name="TelegramOnboardingSession",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("chat_id", models.CharField(db_index=True, max_length=64, unique=True)),
                (
                    "step",
                    models.CharField(
                        choices=[
                            ("await_question", "Await question"),
                            ("await_fio", "Await FIO"),
                            ("await_phone", "Await phone"),
                            ("done", "Done"),
                        ],
                        default="await_question",
                        max_length=32,
                    ),
                ),
                ("question", models.TextField(blank=True, default="")),
                ("first_name", models.CharField(blank=True, default="", max_length=100)),
                ("last_name", models.CharField(blank=True, default="", max_length=100)),
                ("phone", models.CharField(blank=True, default="", max_length=40)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("-updated_at",),
            },
        ),
        migrations.CreateModel(
            name="SuflerHintFeedback",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("operator_name", models.CharField(blank=True, default="", max_length=160)),
                ("query", models.TextField(blank=True, default="")),
                ("hint_rank", models.PositiveSmallIntegerField(default=1)),
                ("hint_text", models.TextField(blank=True, default="")),
                (
                    "choice",
                    models.CharField(
                        choices=[
                            ("used", "Использовал"),
                            ("not_used", "Не использовал"),
                            ("partial", "Частично"),
                        ],
                        max_length=16,
                    ),
                ),
                ("relevance_percent", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("citation_title", models.CharField(blank=True, default="", max_length=255)),
                ("request_id", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "dialog",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sufler_hint_feedback",
                        to="online_chat.dialog",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="operatorassignmenthold",
            index=models.Index(
                fields=["operator", "until"], name="online_chat_operato_hold_idx"
            ),
        ),
    ]
