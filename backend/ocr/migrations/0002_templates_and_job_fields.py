from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("ocr", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="ocrjob",
            name="document_type",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="ocrjob",
            name="validation_status",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.CreateModel(
            name="OcrDocumentTemplate",
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
                ("doc_type", models.SlugField(max_length=64, unique=True)),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("template_version", models.PositiveIntegerField(default=1)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("published", "Published"),
                            ("archived", "Archived"),
                        ],
                        db_index=True,
                        default="draft",
                        max_length=16,
                    ),
                ),
                ("required_fields", models.JSONField(default=list)),
                ("field_schema", models.JSONField(default=dict)),
                ("confidence_min", models.FloatField(default=0.6)),
                ("sample_prompt", models.TextField(blank=True)),
                ("owner", models.CharField(blank=True, max_length=150)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("doc_type",),
            },
        ),
        migrations.CreateModel(
            name="OcrTemplateSample",
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
                ("object_key", models.CharField(blank=True, max_length=512)),
                ("ocr_text", models.TextField(blank=True)),
                ("expected_fields", models.JSONField(default=dict)),
                ("notes", models.TextField(blank=True)),
                ("created_by", models.CharField(blank=True, max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "template",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="samples",
                        to="ocr.ocrdocumenttemplate",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
    ]
