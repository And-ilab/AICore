# Event trigger for Task skill prompts on Capabilities screen.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0005_kb_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="assistantprompttemplate",
            name="event_trigger",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
    ]
