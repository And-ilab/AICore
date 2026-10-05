# Generated manually for FR-CC-08 / FR-CC-13 KB admin.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContactCenterKnowledgeBase",
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
                ("name", models.CharField(max_length=200, unique=True)),
                ("slug", models.SlugField(max_length=200, unique=True)),
                (
                    "scope",
                    models.CharField(default="contact_center", max_length=64),
                ),
                ("description", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
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
                ("status_message", models.CharField(blank=True, max_length=500)),
                ("document_count", models.PositiveIntegerField(default=0)),
                ("chunk_count", models.PositiveIntegerField(default=0)),
                ("last_reindexed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.CharField(blank=True, max_length=150)),
            ],
            options={
                "ordering": ("name",),
            },
        ),
        migrations.CreateModel(
            name="KnowledgeBaseDocument",
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
                        to="hub.contactcenterknowledgebase",
                    ),
                ),
            ],
            options={
                "ordering": ("-uploaded_at",),
            },
        ),
    ]
