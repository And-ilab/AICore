from django.db import migrations


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


def enrich(apps, schema_editor):
    Template = apps.get_model("hub", "AssistantDocumentTemplate")
    slides = Template.objects.filter(name="Презентация (цель / план / выводы)").first()
    if slides is not None:
        slides.body = SLIDES_BODY
        slides.fields = [
            {"id": "title", "label": "Заголовок", "required": False},
            {"id": "topic", "label": "Тема", "required": False},
            {"id": "goal", "label": "Цель", "required": False},
            {"id": "plan", "label": "План", "required": False},
            {"id": "conclusions", "label": "Выводы", "required": False},
        ]
        slides.save(update_fields=["body", "fields", "updated_at"])
    diagram = Template.objects.filter(name="Процесс BPMN").first()
    if diagram is not None:
        diagram.body = BPMN_BODY
        diagram.fields = [
            {"id": "topic", "label": "Суть процесса", "required": False},
        ]
        diagram.save(update_fields=["body", "fields", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0021_assistant_website_crawl"),
    ]

    operations = [
        migrations.RunPython(enrich, migrations.RunPython.noop),
    ]
