from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="OcrJob",
            fields=[
                (
                    "job_id",
                    models.CharField(max_length=64, primary_key=True, serialize=False),
                ),
                ("document_id", models.CharField(db_index=True, max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("ocr_processing", "OCR processing"),
                            ("completed", "Completed"),
                            ("processing_error", "Processing error"),
                        ],
                        db_index=True,
                        default="queued",
                        max_length=32,
                    ),
                ),
                ("filename", models.CharField(max_length=255)),
                ("content_type", models.CharField(blank=True, max_length=128)),
                ("sha256", models.CharField(max_length=64)),
                ("original_object_key", models.CharField(max_length=512)),
                ("result_object_key", models.CharField(blank=True, max_length=512)),
                ("ocr_model", models.CharField(blank=True, max_length=255)),
                ("error_message", models.TextField(blank=True)),
                ("created_by", models.CharField(blank=True, max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
    ]
