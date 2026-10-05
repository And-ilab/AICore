from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="QuReferenceExample",
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
                ("question", models.CharField(max_length=1000)),
                (
                    "article_id",
                    models.BigIntegerField(
                        blank=True,
                        db_index=True,
                        null=True,
                    ),
                ),
                ("intent_id", models.CharField(blank=True, max_length=128)),
                ("locale", models.CharField(default="ru", max_length=8)),
                (
                    "is_active",
                    models.BooleanField(default=True, db_index=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ("id",)},
        ),
    ]
