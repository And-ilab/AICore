from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0019_telegram_onboarding_meta"),
    ]

    operations = [
        migrations.AddField(
            model_name="dialog",
            name="client_fields",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
