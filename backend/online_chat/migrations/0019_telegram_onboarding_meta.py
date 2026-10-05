from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0018_operator_photo_textfield"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramonboardingsession",
            name="meta",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
