from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hub", "0031_seed_more_operator_scenarios"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssistantAnswerFeedback",
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
                    "username",
                    models.CharField(blank=True, default="", max_length=150),
                ),
                (
                    "session_id",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                ("message_id", models.CharField(max_length=64)),
                ("question", models.TextField(blank=True, default="")),
                ("answer_text", models.TextField(blank=True, default="")),
                (
                    "choice",
                    models.CharField(
                        choices=[
                            ("useful", "Воспользовался"),
                            ("incomplete", "Неполный ответ"),
                            ("incorrect", "Не воспользовался"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "relevance_percent",
                    models.PositiveSmallIntegerField(blank=True, null=True),
                ),
                ("article_id", models.BigIntegerField(blank=True, null=True)),
                (
                    "article_title",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Assistant answer feedback",
                "verbose_name_plural": "Assistant answer feedback",
                "ordering": ("-created_at", "-id"),
            },
        ),
        migrations.AddConstraint(
            model_name="assistantanswerfeedback",
            constraint=models.UniqueConstraint(
                fields=("username", "message_id"),
                name="assistant_feedback_user_message_uniq",
            ),
        ),
    ]
