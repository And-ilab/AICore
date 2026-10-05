import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")
django.setup()

from hub.models import AssistantKnowledgeBase, AssistantKnowledgeBaseDocument, ContactCenterKnowledgeBase

print("ASSISTANT", AssistantKnowledgeBase.objects.count())
for kb in AssistantKnowledgeBase.objects.all().order_by("pk"):
    print(f"A {kb.pk}|{kb.name}|docs={kb.documents.count()}|chunks={kb.chunk_count}")
print("CC", ContactCenterKnowledgeBase.objects.count())
for kb in ContactCenterKnowledgeBase.objects.all().order_by("pk"):
    print(f"C {kb.pk}|{kb.name}|docs={kb.documents.count()}")

doc = AssistantKnowledgeBaseDocument.objects.filter(filename__icontains="avtokredit").first()
text = (doc.extracted_text or "") if doc else ""
print("AUTO_LEN", len(text), "FILE", getattr(doc, "filename", None))
print("---AUTO---")
print(text[:7000])
