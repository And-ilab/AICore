from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0014_base_messages_bot_offline"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceLevelSettings",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                (
                    "first_response_seconds",
                    models.PositiveIntegerField(
                        default=120,
                        help_text="Целевое время первого ответа оператора, секунды",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Service level settings",
                "verbose_name_plural": "Service level settings",
            },
        ),
    ]
