from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0011_sufler_policy_max_hints"),
    ]

    operations = [
        migrations.CreateModel(
            name="DialogScenario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=32, unique=True)),
                ("title", models.CharField(max_length=200)),
                ("root_question", models.CharField(blank=True, default="", max_length=500)),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Черновик"), ("production", "Опубликован")],
                        db_index=True,
                        default="draft",
                        max_length=16,
                    ),
                ),
                (
                    "channels",
                    models.CharField(
                        choices=[
                            ("both", "Телефония и чат"),
                            ("telephony", "Телефония"),
                            ("online_chat", "Онлайн-чат"),
                        ],
                        default="both",
                        max_length=32,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.CharField(blank=True, default="", max_length=150)),
            ],
            options={"ordering": ("code",)},
        ),
        migrations.CreateModel(
            name="DialogScenarioVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version_number", models.PositiveIntegerField(default=1)),
                ("graph", models.JSONField(default=dict)),
                ("system_prompt", models.TextField(blank=True, default="")),
                ("is_published", models.BooleanField(default=False)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.CharField(blank=True, default="", max_length=150)),
                (
                    "scenario",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="versions",
                        to="hub.dialogscenario",
                    ),
                ),
            ],
            options={"ordering": ("-version_number",)},
        ),
        migrations.AddField(
            model_name="dialogscenario",
            name="current_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="+",
                to="hub.dialogscenarioversion",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="dialogscenarioversion",
            unique_together={("scenario", "version_number")},
        ),
        migrations.CreateModel(
            name="DialogScenarioSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_key", models.CharField(max_length=160, unique=True)),
                ("node_id", models.CharField(max_length=64)),
                ("path", models.JSONField(default=list)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "scenario",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="sessions",
                        to="hub.dialogscenario",
                    ),
                ),
            ],
            options={"ordering": ("-updated_at",)},
        ),
    ]
