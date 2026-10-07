from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hub", "0027_merge_sql_and_caller_memory"),
    ]

    operations = [
        migrations.CreateModel(
            name="SlotModelSelection",
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
                ("slot", models.CharField(max_length=64, unique=True)),
                ("model_id", models.CharField(max_length=200)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.CharField(blank=True, max_length=150)),
            ],
            options={
                "verbose_name": "Slot model selection",
                "verbose_name_plural": "Slot model selections",
                "ordering": ("slot",),
            },
        ),
    ]
