from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("online_chat", "0007_channel_delivery"),
    ]

    operations = [
        migrations.AddField(
            model_name="dialogmessage",
            name="attachment_content_type",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="dialogmessage",
            name="attachment_key",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="dialogmessage",
            name="attachment_scan_status",
            field=models.CharField(
                db_index=True,
                default="not_required",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="dialogmessage",
            name="attachment_size",
            field=models.PositiveBigIntegerField(default=0),
        ),
    ]
