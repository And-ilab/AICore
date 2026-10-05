import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")
django.setup()
from hub.models import AssistantKnowledgeBaseDocument
from ingest.models import AssistantProductionChunk
title = "\u041f\u043e\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u043e \u0441\u043b\u0443\u0436\u0435\u0431\u043d\u044b\u0445 \u043a\u043e\u043c\u0430\u043d\u0434\u0438\u0440\u043e\u0432\u043a\u0430\u0445"
for document in AssistantKnowledgeBaseDocument.objects.filter(filename__contains="28.9"):
    updated = AssistantProductionChunk.objects.filter(
        kb_slug=document.knowledge_base.slug,
        article_id=document.article_id,
    ).update(title=title)
    document.filename = title + ".doc"
    document.save(update_fields=("filename",))
    print("RENAMED", updated)
print("LEFT_DONE")
