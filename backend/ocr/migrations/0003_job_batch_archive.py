from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ocr", "0002_templates_and_job_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="ocrjob",
            name="batch_id",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="ocrjob",
            name="source_archive",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
