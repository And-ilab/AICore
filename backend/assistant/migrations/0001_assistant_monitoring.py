from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AssistantReportTemplate",
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
                ("name", models.CharField(max_length=200)),
                ("metrics", models.JSONField(default=list)),
                (
                    "export_format",
                    models.CharField(
                        choices=[("csv", "CSV"), ("xlsx", "XLSX")],
                        default="csv",
                        max_length=8,
                    ),
                ),
                (
                    "created_by_id",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Assistant report template",
                "verbose_name_plural": "Assistant report templates",
                "ordering": ("name", "id"),
            },
        ),
        migrations.CreateModel(
            name="AssistantRequestEvent",
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
                ("request_id", models.CharField(max_length=64, unique=True)),
                (
                    "message_id",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                (
                    "session_id",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                (
                    "username",
                    models.CharField(blank=True, default="", max_length=150),
                ),
                (
                    "department",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "query_type",
                    models.CharField(
                        choices=[
                            ("rag_kb", "Поиск по базе"),
                            ("attachment_summary", "Резюме вложения"),
                            ("skill", "Навык"),
                            ("no_kb", "Нет данных в базе"),
                            ("content_filter", "Фильтр контента"),
                            ("llm_error", "Ошибка модели"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "topic",
                    models.CharField(default="без источника", max_length=255),
                ),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("streamed", "Ответ отдан"),
                            ("no_kb", "Нет фрагментов"),
                            ("content_filter", "Отказ фильтра"),
                            ("llm_error", "Ошибка модели"),
                            ("client_closed", "Клиент прервал"),
                            ("error", "Сбой"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "error_reason",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("", ""),
                            ("no_sources", "Нет данных в базе"),
                            ("low_relevance", "Релевантность ниже порога"),
                            ("llm_error", "Ошибка модели"),
                            ("content_filter", "Отказ фильтра"),
                        ],
                        default="",
                        max_length=32,
                    ),
                ),
                ("total_ms", models.FloatField(blank=True, null=True)),
                ("ttft_ms", models.FloatField(blank=True, null=True)),
                ("llm_ms", models.FloatField(blank=True, null=True)),
                ("top_relevance", models.FloatField(blank=True, null=True)),
                ("doc_count", models.PositiveIntegerField(default=0)),
                ("token_count", models.PositiveIntegerField(blank=True, null=True)),
                ("kb_slugs", models.JSONField(blank=True, default=list)),
                (
                    "source_title",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                ("question_text", models.TextField(blank=True, default="")),
                ("answer_text", models.TextField(blank=True, default="")),
                ("hallucination_marked", models.BooleanField(default=False)),
                (
                    "hallucination_marked_by_id",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                (
                    "hallucination_marked_at",
                    models.DateTimeField(blank=True, null=True),
                ),
            ],
            options={
                "verbose_name": "Assistant request event",
                "verbose_name_plural": "Assistant request events",
                "ordering": ("-created_at", "-id"),
                "indexes": [
                    models.Index(
                        fields=["created_at", "department"],
                        name="ass_mon_evt_created_dept_idx",
                    ),
                    models.Index(
                        fields=["created_at", "query_type"],
                        name="ass_mon_evt_created_type_idx",
                    ),
                    models.Index(
                        fields=["created_at", "outcome"],
                        name="ass_mon_evt_created_out_idx",
                    ),
                    models.Index(fields=["message_id"], name="ass_mon_evt_message_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AssistantReportSchedule",
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
                    "cadence",
                    models.CharField(
                        choices=[
                            ("daily", "Ежедневно"),
                            ("weekly", "Еженедельно"),
                            ("monthly", "Ежемесячно"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "report_id",
                    models.CharField(blank=True, default="", max_length=32),
                ),
                ("enabled", models.BooleanField(default=True)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                (
                    "last_status",
                    models.CharField(
                        choices=[
                            ("never", "Не запускалось"),
                            ("ok", "Готово"),
                            ("error", "Ошибка"),
                        ],
                        default="never",
                        max_length=16,
                    ),
                ),
                (
                    "last_error",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                ("last_summary", models.JSONField(blank=True, default=dict)),
                (
                    "created_by_id",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "template",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="schedules",
                        to="assistant.assistantreporttemplate",
                    ),
                ),
            ],
            options={
                "verbose_name": "Assistant report schedule",
                "verbose_name_plural": "Assistant report schedules",
                "ordering": ("cadence", "id"),
            },
        ),
    ]
