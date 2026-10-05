from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0002_close_feedback_transcript"),
    ]

    operations = [
        migrations.AddField(
            model_name="dialogmessage",
            name="receipt_status",
            field=models.CharField(
                choices=[("delivered", "Доставлено"), ("read", "Прочитано")],
                db_index=True,
                default="delivered",
                max_length=16,
            ),
        ),
    ]
