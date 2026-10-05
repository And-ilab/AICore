from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("ocr", "0003_job_batch_archive"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OcrUserTemplate",
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
                ("name", models.CharField(max_length=80)),
                ("name_key", models.CharField(max_length=80)),
                ("fields", models.JSONField(default=list)),
                ("source_job_id", models.CharField(blank=True, max_length=64)),
                ("source_file", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ocr_user_templates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("name", "id"),
            },
        ),
        migrations.AddConstraint(
            model_name="ocrusertemplate",
            constraint=models.UniqueConstraint(
                fields=("owner", "name_key"),
                name="uniq_ocr_user_template_owner_name",
            ),
        ),
        migrations.AddField(
            model_name="ocrjob",
            name="user_template",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="jobs",
                to="ocr.ocrusertemplate",
            ),
        ),
    ]
