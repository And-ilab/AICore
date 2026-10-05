from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ModelRegistrySettings",
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
                (
                    "profile",
                    models.CharField(
                        choices=[
                            ("assistant_bank", "Assistant Bank"),
                            ("sufler_cc", "Sufler Contact Center"),
                        ],
                        max_length=32,
                        unique=True,
                    ),
                ),
                ("temperature", models.FloatField()),
                ("top_p", models.FloatField()),
                ("max_tokens", models.PositiveIntegerField()),
                ("response_chars_max", models.PositiveIntegerField()),
                ("chunk_size_tokens", models.PositiveIntegerField()),
                ("chunk_overlap_tokens", models.PositiveIntegerField()),
                ("context_inclusion_threshold", models.FloatField()),
                ("deterministic_answer_threshold", models.FloatField()),
                ("revision", models.PositiveIntegerField(default=1)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.CharField(blank=True, max_length=150)),
            ],
            options={
                "verbose_name": "Model Registry settings",
                "verbose_name_plural": "Model Registry settings",
                "ordering": ("profile",),
            },
        ),
    ]
