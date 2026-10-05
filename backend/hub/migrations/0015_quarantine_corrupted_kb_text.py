import unicodedata

from django.db import migrations


def _is_ru_en_letter(character):
    codepoint = ord(character)
    return (
        0x0041 <= codepoint <= 0x005A
        or 0x0061 <= codepoint <= 0x007A
        or 0x00C0 <= codepoint <= 0x024F
        or 0x0400 <= codepoint <= 0x052F
        or 0x1E00 <= codepoint <= 0x1EFF
    )


def _is_corrupted(text):
    return any(
        unicodedata.category(character).startswith("L")
        and not _is_ru_en_letter(character)
        for character in (text or "")
    )


def quarantine_corrupted_text(apps, schema_editor):
    CCProductionChunk = apps.get_model("ingest", "CCProductionChunk")
    AssistantProductionChunk = apps.get_model("ingest", "AssistantProductionChunk")
    KnowledgeBaseDocument = apps.get_model("hub", "KnowledgeBaseDocument")
    AssistantKnowledgeBaseDocument = apps.get_model(
        "hub", "AssistantKnowledgeBaseDocument"
    )

    corrupted_article_ids = set()
    for chunk in CCProductionChunk.objects.filter(is_active=True).iterator():
        if _is_corrupted(chunk.title) or _is_corrupted(chunk.content):
            chunk.is_active = False
            chunk.save(update_fields=["is_active"])
            corrupted_article_ids.add(chunk.article_id)

    for chunk in AssistantProductionChunk.objects.filter(is_active=True).iterator():
        if _is_corrupted(chunk.title) or _is_corrupted(chunk.content):
            chunk.is_active = False
            chunk.save(update_fields=["is_active"])
            corrupted_article_ids.add(chunk.article_id)

    message = (
        "Карантин: обнаружен повреждённый текст или символы вне русского "
        "и английского алфавитов. Перезагрузите документ как DOCX/PDF."
    )
    for model in (KnowledgeBaseDocument, AssistantKnowledgeBaseDocument):
        for document in model.objects.all().iterator():
            if (
                document.article_id in corrupted_article_ids
                or _is_corrupted(document.extracted_text)
            ):
                document.status = "error"
                document.status_message = message
                document.chunk_count = 0
                document.save(
                    update_fields=["status", "status_message", "chunk_count"]
                )


class Migration(migrations.Migration):
    dependencies = [
        ("ingest", "0004_assistant_production"),
        ("hub", "0014_seed_scenario_qu_examples"),
    ]

    operations = [
        migrations.RunPython(
            quarantine_corrupted_text,
            migrations.RunPython.noop,
        ),
    ]
