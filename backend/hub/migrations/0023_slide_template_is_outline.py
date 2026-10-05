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


def outline(apps, schema_editor):
    Template = apps.get_model("hub", "AssistantDocumentTemplate")
    for slides in Template.objects.filter(output_format="pptx"):
        body = slides.body or ""
        if "Суфлёр на звонке" in body or slides.name == "Презентация (цель / план / выводы)":
            slides.body = SLIDES_BODY
            slides.save(update_fields=["body", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0022_richer_slide_and_bpmn_templates"),
    ]

    operations = [
        migrations.RunPython(outline, migrations.RunPython.noop),
    ]
