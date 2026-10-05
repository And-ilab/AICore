from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("online_chat", "0006_channel_identity"),
    ]

    operations = [
        migrations.AddField(
            model_name="dialogmessage",
            name="channel_delivery_error",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="dialogmessage",
            name="channel_delivery_status",
            field=models.CharField(
                choices=[
                    ("not_required", "Не требуется"),
                    ("pending", "Ожидает отправки"),
                    ("sent", "Отправлено в канал"),
                    ("failed", "Ошибка доставки"),
                ],
                db_index=True,
                default="not_required",
                max_length=16,
            ),
        ),
    ]
