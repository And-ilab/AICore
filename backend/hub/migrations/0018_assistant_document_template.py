from django.db import migrations, models


LEAVE_BODY = """Заявление

Я, {{full_name}}, прошу предоставить ежегодный оплачиваемый отпуск.

Подразделение: {{department}}
Дата начала отпуска: {{start_date}}

С уважением,
{{full_name}}
"""

MEMO_BODY = """Служебная записка

От: {{full_name}}
Подразделение: {{department}}
Дата: {{memo_date}}

Тема: {{subject}}

{{body_text}}
"""


def seed_templates(apps, schema_editor):
    Template = apps.get_model("hub", "AssistantDocumentTemplate")
    if Template.objects.filter(name="Заявление на отпуск").exists():
        return
    Template.objects.create(
        name="Заявление на отпуск",
        category="Кадры",
        output_format="docx",
        body=LEAVE_BODY,
        fields=[
            {"id": "full_name", "label": "ФИО", "required": True},
            {"id": "department", "label": "Подразделение", "required": True},
            {"id": "start_date", "label": "Дата начала", "required": True},
        ],
        active=True,
        updated_by="system",
    )
    Template.objects.create(
        name="Служебная записка",
        category="Канцелярия",
        output_format="pdf",
        body=MEMO_BODY,
        fields=[
            {"id": "full_name", "label": "ФИО", "required": True},
            {"id": "department", "label": "Подразделение", "required": True},
            {"id": "memo_date", "label": "Дата", "required": True},
            {"id": "subject", "label": "Тема", "required": True},
            {"id": "body_text", "label": "Текст", "required": False},
        ],
        active=True,
        updated_by="system",
    )


def unseed_templates(apps, schema_editor):
    Template = apps.get_model("hub", "AssistantDocumentTemplate")
    Template.objects.filter(
        name__in=["Заявление на отпуск", "Служебная записка"],
        updated_by="system",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0017_scenario_session_pause"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssistantDocumentTemplate",
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
                ("category", models.CharField(default="Общее", max_length=64)),
                (
                    "output_format",
                    models.CharField(
                        choices=[
                            ("docx", "Word"),
                            ("pdf", "PDF"),
                            ("xlsx", "Excel"),
                            ("pptx", "PowerPoint"),
                            ("bpmn", "BPMN"),
                        ],
                        db_index=True,
                        default="docx",
                        max_length=8,
                    ),
                ),
                (
                    "body",
                    models.TextField(
                        help_text="Текст бланка. Поля подставляются как {{field_id}}.",
                    ),
                ),
                ("fields", models.JSONField(blank=True, default=list)),
                ("active", models.BooleanField(db_index=True, default=True)),
                ("updated_by", models.CharField(blank=True, max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("category", "name"),
            },
        ),
        migrations.RunPython(seed_templates, unseed_templates),
    ]
