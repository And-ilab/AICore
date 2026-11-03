from django.db import migrations, models


def seed_content_filters(apps, schema_editor):
    from hub.content_filters import seed_default_content_filters

    seed_default_content_filters(username="0029_seed")


class Migration(migrations.Migration):

    dependencies = [
        ("hub", "0028_slot_model_selection"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssistantContentFilter",
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
                ("code", models.SlugField(max_length=32, unique=True)),
                ("name", models.CharField(max_length=80)),
                ("enabled", models.BooleanField(default=True)),
                ("keywords", models.JSONField(default=list)),
                ("exceptions", models.JSONField(default=list)),
                ("refusal_text", models.TextField()),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.CharField(blank=True, default="", max_length=150),
                ),
            ],
            options={
                "verbose_name": "Assistant content filter",
                "verbose_name_plural": "Assistant content filters",
                "ordering": ("sort_order", "code"),
            },
        ),
        migrations.RunPython(seed_content_filters, migrations.RunPython.noop),
    ]
