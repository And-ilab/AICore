from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0025_work_schedule_last_open_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="dialog",
            name="client_ip",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
    ]
