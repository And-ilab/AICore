from django.db import migrations, models


MEMO_TXT = """Служебная записка

Тема: {{subject}}
Дата: {{memo_date}}
От: {{full_name}}, {{department}}

{{body_text}}
"""

CERTIFICATE_TXT = """Справка

Настоящая справка выдана {{full_name}} ({{department}}).

Содержание: {{subject}}

Дата выдачи: {{issue_date}}
"""

REPORT_TXT = """Краткий отчёт

Тема: {{subject}}
Дата: {{memo_date}}
Подготовил: {{full_name}}

{{body_text}}
"""

SLIDES_BODY = """## Введение
Один слайд. О чём статья.

## Содержание
Слайды по статье. Сколько нужно, чтобы покрыть материал: глава или отдельный блок — отдельный слайд. Число не задаётся.

## Цель
Один слайд. Зачем это слушателю, только по статье.

## План
Один слайд. Что из статьи делать дальше.

## Выводы
Один слайд. Что следует из статьи.
"""

BPMN_BODY = """Родитель просит карту ребёнку
Оператор уточняет возраст и кто обращается
Проверка паспорта родителя и свидетельства о рождении
Суфлёр показывает комплект документов и лимит
Руководитель согласует, если комплекта не хватает
Отделение выпускает карту
Клиент получает карту и памятку
"""

ER_BODY = """{{entities}}
"""


def seed(apps, schema_editor):
    Template = apps.get_model("hub", "AssistantDocumentTemplate")
    specs = [
        {
            "name": "Служебная записка (текст)",
            "category": "Текст",
            "output_format": "txt",
            "body": MEMO_TXT,
            "fields": [
                {"id": "subject", "label": "Тема", "required": True},
                {"id": "full_name", "label": "ФИО", "required": False},
                {"id": "department", "label": "Подразделение", "required": False},
                {"id": "memo_date", "label": "Дата", "required": False},
                {"id": "body_text", "label": "Текст", "required": False},
            ],
        },
        {
            "name": "Справка (текст)",
            "category": "Текст",
            "output_format": "txt",
            "body": CERTIFICATE_TXT,
            "fields": [
                {"id": "subject", "label": "Содержание", "required": True},
                {"id": "full_name", "label": "ФИО", "required": False},
                {"id": "department", "label": "Подразделение", "required": False},
                {"id": "issue_date", "label": "Дата выдачи", "required": False},
            ],
        },
        {
            "name": "Краткий отчёт (текст)",
            "category": "Текст",
            "output_format": "txt",
            "body": REPORT_TXT,
            "fields": [
                {"id": "subject", "label": "Тема", "required": True},
                {"id": "full_name", "label": "Автор", "required": False},
                {"id": "memo_date", "label": "Дата", "required": False},
                {"id": "body_text", "label": "Текст", "required": False},
            ],
        },
        {
            "name": "Презентация (цель / план / выводы)",
            "category": "Презентации",
            "output_format": "pptx",
            "body": SLIDES_BODY,
            "fields": [
                {"id": "title", "label": "Заголовок", "required": False},
                {"id": "topic", "label": "Тема", "required": False},
                {"id": "goal", "label": "Цель", "required": False},
                {"id": "plan", "label": "План", "required": False},
                {"id": "conclusions", "label": "Выводы", "required": False},
            ],
        },
        {
            "name": "Процесс BPMN",
            "category": "Диаграммы",
            "output_format": "bpmn",
            "body": BPMN_BODY,
            "fields": [
                {"id": "topic", "label": "Суть процесса", "required": False},
            ],
        },
        {
            "name": "ER-диаграмма",
            "category": "Диаграммы",
            "output_format": "mmd",
            "body": ER_BODY,
            "fields": [
                {"id": "entities", "label": "Сущности (по строке)", "required": True},
            ],
        },
    ]
    for spec in specs:
        if Template.objects.filter(name=spec["name"]).exists():
            continue
        Template.objects.create(updated_by="system", active=True, **spec)


def unseed(apps, schema_editor):
    Template = apps.get_model("hub", "AssistantDocumentTemplate")
    Template.objects.filter(
        name__in=[
            "Служебная записка (текст)",
            "Справка (текст)",
            "Краткий отчёт (текст)",
            "Презентация (цель / план / выводы)",
            "Процесс BPMN",
            "ER-диаграмма",
        ],
        updated_by="system",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0018_assistant_document_template"),
    ]

    operations = [
        migrations.AlterField(
            model_name="assistantdocumenttemplate",
            name="output_format",
            field=models.CharField(
                choices=[
                    ("docx", "Word"),
                    ("pdf", "PDF"),
                    ("xlsx", "Excel"),
                    ("pptx", "PowerPoint"),
                    ("bpmn", "BPMN"),
                    ("txt", "Текст"),
                    ("mmd", "Схема / ER"),
                ],
                db_index=True,
                default="docx",
                max_length=8,
            ),
        ),
        migrations.RunPython(seed, unseed),
    ]
