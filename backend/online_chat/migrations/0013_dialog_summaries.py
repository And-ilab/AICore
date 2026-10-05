from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0012_rename_assignment_hold_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="dialog",
            name="summary_detailed",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="dialog",
            name="summary_short",
            field=models.TextField(blank=True, default=""),
        ),
    ]
