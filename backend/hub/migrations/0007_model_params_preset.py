# Preset field for LLM model params (§3.3.2).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0006_prompt_event_trigger"),
    ]

    operations = [
        migrations.AddField(
            model_name="modelregistrysettings",
            name="preset",
            field=models.CharField(
                choices=[
                    ("short", "Краткий"),
                    ("standard", "Стандарт"),
                    ("long", "Развёрнутый"),
                ],
                default="standard",
                max_length=16,
            ),
        ),
    ]
