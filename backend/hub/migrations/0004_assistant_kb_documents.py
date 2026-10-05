# Generated manually for assistant_* KB document upload

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("hub", "0003_assistant_admin_stubs"),
    ]

    operations = [
        migrations.AddField(
            model_name="assistantknowledgebase",
            name="chunk_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="assistantknowledgebase",
            name="last_reindexed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="assistantknowledgebase",
            name="status_message",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AlterField(
            model_name="assistantknowledgebase",
            name="status",
            field=models.CharField(
                choices=[
                    ("idle", "Idle"),
                    ("indexing", "Indexing"),
                    ("ready", "Ready"),
                    ("error", "Error"),
                ],
                db_index=True,
                default="idle",
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="AssistantKnowledgeBaseDocument",
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
                ("filename", models.CharField(max_length=255)),
                ("content_type", models.CharField(blank=True, max_length=128)),
                ("size_bytes", models.PositiveIntegerField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("uploaded", "Uploaded"),
                            ("indexed", "Indexed"),
                            ("error", "Error"),
                        ],
                        db_index=True,
                        default="uploaded",
                        max_length=16,
                    ),
                ),
                ("status_message", models.CharField(blank=True, max_length=500)),
                ("extracted_text", models.TextField(blank=True)),
                ("chunk_count", models.PositiveIntegerField(default=0)),
                ("article_id", models.BigIntegerField(unique=True)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("indexed_at", models.DateTimeField(blank=True, null=True)),
                ("uploaded_by", models.CharField(blank=True, max_length=150)),
                (
                    "knowledge_base",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="hub.assistantknowledgebase",
                    ),
                ),
            ],
            options={
                "ordering": ("-uploaded_at",),
            },
        ),
    ]
