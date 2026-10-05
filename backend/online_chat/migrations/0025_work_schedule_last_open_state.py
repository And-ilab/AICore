from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0024_dialog_close_topics_v2"),
    ]

    operations = [
        migrations.AddField(
            model_name="workschedulesettings",
            name="last_open_state",
            field=models.BooleanField(blank=True, default=None, null=True),
        ),
    ]
