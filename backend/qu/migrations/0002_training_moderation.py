import hashlib
import re

from django.db import migrations, models
from django.utils import timezone


def backfill_question_hashes(apps, schema_editor):
    example_model = apps.get_model("qu", "QuReferenceExample")
    whitespace = re.compile(r"\s+")
    for item in example_model.objects.all():
        normalized = whitespace.sub(" ", (item.question or "").casefold()).strip()
        item.question_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if not item.status:
            item.status = "active"
        item.save(update_fields=["question_hash", "status"])


class Migration(migrations.Migration):
    dependencies = [
        ("qu", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="qureferenceexample",
            name="admin_comment",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="qureferenceexample",
            name="article_title",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="qureferenceexample",
            name="channel",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="qureferenceexample",
            name="created_by",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
        migrations.AddField(
            model_name="qureferenceexample",
            name="operator_name",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AddField(
            model_name="qureferenceexample",
            name="original_hint",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="qureferenceexample",
            name="question_hash",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="qureferenceexample",
            name="relevance_percent",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="qureferenceexample",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="qureferenceexample",
            name="reviewed_by",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
        migrations.AddField(
            model_name="qureferenceexample",
            name="source",
            field=models.CharField(
                choices=[
                    ("manual", "Ручное добавление"),
                    ("dialog", "Диалог"),
                    ("asr_qa", "QA ASR"),
                ],
                db_index=True,
                default="manual",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="qureferenceexample",
            name="source_feedback_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="qureferenceexample",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Активен"),
                    ("pending_review", "На модерации"),
                    ("rejected", "Отклонён"),
                ],
                db_index=True,
                default="active",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="qureferenceexample",
            name="synonyms",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="qureferenceexample",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=timezone.now),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name="qureferenceexample",
            options={"ordering": ("-updated_at", "-id")},
        ),
        migrations.CreateModel(
            name="QuReplenishmentPolicy",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "mode",
                    models.CharField(
                        choices=[
                            ("suggest", "Предлагать (без автозаписи)"),
                            ("auto_with_confirmation", "Черновик на модерацию"),
                            ("auto", "Автодобавление"),
                        ],
                        default="auto_with_confirmation",
                        max_length=32,
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.CharField(blank=True, default="", max_length=150)),
            ],
            options={
                "verbose_name": "QU replenishment policy",
                "verbose_name_plural": "QU replenishment policies",
            },
        ),
        migrations.RunPython(backfill_question_hashes, migrations.RunPython.noop),
    ]
