import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")
django.setup()

from hub.models import AssistantKnowledgeBase
from ingest.models import AssistantProductionChunk

for kb in AssistantKnowledgeBase.objects.all().order_by("name"):
    docs = list(kb.documents.all())
    chunks = AssistantProductionChunk.objects.filter(kb_slug=kb.slug, is_active=True).count()
    print(f"KB id={kb.pk} slug={kb.slug} status={kb.status} chunks={chunks} name={kb.name}")
    for doc in docs:
        print(
            f"  doc id={doc.pk} chunks={doc.chunk_count} status={doc.status} "
            f"bytes={doc.size_bytes} file={doc.filename}"
        )
