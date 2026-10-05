from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0021_work_schedule_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="workschedulesettings",
            name="day_overrides",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
