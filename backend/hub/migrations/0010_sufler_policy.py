from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0009_sufler_training"),
    ]

    operations = [
        migrations.CreateModel(
            name="SuflerPolicy",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("telephony_min_relevance_percent", models.PositiveSmallIntegerField(default=20)),
                ("chat_min_relevance_percent", models.PositiveSmallIntegerField(default=20)),
                ("clarify_min_relevance_percent", models.PositiveSmallIntegerField(default=15)),
                ("max_hints", models.PositiveSmallIntegerField(default=2)),
                (
                    "default_mode",
                    models.CharField(
                        choices=[
                            ("consultation", "Консультация"),
                            ("service", "Услуга"),
                        ],
                        default="consultation",
                        max_length=16,
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.CharField(blank=True, default="", max_length=150)),
            ],
            options={
                "verbose_name": "Sufler policy",
                "verbose_name_plural": "Sufler policies",
            },
        ),
    ]
