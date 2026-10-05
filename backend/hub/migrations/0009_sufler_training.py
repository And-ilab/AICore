from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0008_assistant_doc_original_path"),
    ]

    operations = [
        migrations.CreateModel(
            name="SuflerTrainingExample",
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
                ("query", models.TextField()),
                ("original_hint", models.TextField(blank=True, default="")),
                ("feedback_choice", models.CharField(default="not_used", max_length=16)),
                ("correct_answer", models.TextField()),
                ("admin_prompt", models.TextField(blank=True, default="")),
                ("operator_name", models.CharField(blank=True, default="", max_length=160)),
                (
                    "feedback_id",
                    models.CharField(blank=True, db_index=True, default="", max_length=64),
                ),
                ("created_by", models.CharField(blank=True, default="", max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("-updated_at",),
                "verbose_name": "Sufler training example",
                "verbose_name_plural": "Sufler training examples",
            },
        ),
    ]
