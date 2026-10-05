from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("online_chat", "0009_bot_configuration"),
    ]

    operations = [
        migrations.AddField(
            model_name="dialogmessage",
            name="response_origin",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="dialogmessage",
            name="sufler_suggestion_text",
            field=models.TextField(blank=True, default=""),
        ),
    ]
