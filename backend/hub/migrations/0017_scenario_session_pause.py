from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0016_backfill_scenario_edge_replies"),
    ]

    operations = [
        migrations.AddField(
            model_name="dialogscenariosession",
            name="paused",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="dialogscenariosession",
            name="off_topic_count",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
