import json
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402
from django.test import Client, TestCase  # noqa: E402

from assistant.chat import _citation  # noqa: E402
from auth.roles import ROLES_BY_CODE  # noqa: E402
from hub.models import AssistantKnowledgeBase, AssistantWebsitePage  # noqa: E402
from hub.website_crawl import run_website_crawl  # noqa: E402
from ingest.models import AssistantProductionChunk, CCProductionChunk  # noqa: E402
from ingest.web_fetcher import RawHttpResponse  # noqa: E402


SITE = {
    "https://docs.example.com/robots.txt": (200, "text/plain", b"User-agent: *\nAllow: /\n"),
    "https://docs.example.com/sitemap.xml": (
        200,
        "application/xml",
        b"<?xml version='1.0'?><urlset><url><loc>https://docs.example.com/about</loc></url></urlset>",
    ),
    "https://docs.example.com/": (
        200,
        "text/html",
        (
            "<html><title>Visa page</title>"
            "<p>Въездная виза оплачивается банком при командировке.</p>"
            "<a href='/about'>about</a></html>"
        ).encode("utf-8"),
    ),
    "https://docs.example.com/about": (
        200,
        "text/html",
        "<html><title>About</title><p>О банке и командировках за границу.</p></html>".encode(
            "utf-8"
        ),
    ),
}


def mock_http(url: str) -> RawHttpResponse:
    status, ctype, body = SITE.get(url, (404, "text/plain", b"missing"))
    return RawHttpResponse(status, ctype, body, url)


class AssistantWebsiteCrawlTest(TestCase):
    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"web-crawl-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def test_mock_crawl_indexes_permalink_and_keeps_citation(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_module_administrator"))
        created = client.post(
            "/api/admin/assistant/kb/",
            data=json.dumps(
                {
                    "name": "Bank site",
                    "slug": "bank_site",
                    "source": "website",
                    "start_url": "https://docs.example.com/",
                    "allowed_hosts": ["docs.example.com"],
                    "depth": 2,
                    "max_pages": 10,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        kb_id = created.json()["id"]
        empty = client.post(
            "/api/admin/assistant/kb/",
            data=json.dumps(
                {
                    "name": "No hosts",
                    "source": "website",
                    "start_url": "https://docs.example.com/",
                    "allowed_hosts": [],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(empty.status_code, 400)

        started = client.post(
            f"/api/admin/assistant/kb/{kb_id}/crawl/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(started.status_code, 202, started.content)
        job_id = started.json()["job"]["id"]
        run_website_crawl(job_id, http_get=mock_http)

        kb = AssistantKnowledgeBase.objects.get(pk=kb_id)
        self.assertEqual(kb.status, AssistantKnowledgeBase.STATUS_READY)
        pages = list(AssistantWebsitePage.objects.filter(knowledge_base=kb))
        self.assertGreaterEqual(len(pages), 2)
        chunks = list(AssistantProductionChunk.objects.filter(kb_slug=kb.slug))
        self.assertTrue(chunks)
        self.assertTrue(all(item.permalink.startswith("https://docs.example.com") for item in chunks))
        self.assertFalse(CCProductionChunk.objects.filter(permalink__contains="docs.example.com").exists())

        first_id = pages[0].article_id
        run_website_crawl(job_id, http_get=mock_http)
        self.assertEqual(
            AssistantWebsitePage.objects.filter(knowledge_base=kb, article_id=first_id).count(),
            1,
        )
        self.assertEqual(
            AssistantWebsitePage.objects.filter(knowledge_base=kb).count(),
            len(pages),
        )

        self.assertTrue(
            AssistantProductionChunk.objects.filter(
                kb_slug=kb.slug,
                content__icontains="виза",
            ).exists()
        )
        citation = _citation(
            {
                "kb_slug": kb.slug,
                "article_id": chunks[0].article_id,
                "chunk_index": 0,
                "title": chunks[0].title,
                "permalink": chunks[0].permalink,
                "snippet": chunks[0].content[:80],
            }
        )
        self.assertTrue(citation["permalink"].startswith("https://docs.example.com"))
        self.assertNotIn("/api/v1/assistant/sources/download", citation["permalink"])

        status = client.get(f"/api/admin/assistant/kb/{kb_id}/crawl/")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["job"]["status"], "ready")

    def test_zero_pages_marks_job_failed(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_module_administrator"))
        created = client.post(
            "/api/admin/assistant/kb/",
            data=json.dumps(
                {
                    "name": "Empty site",
                    "slug": "empty_site",
                    "source": "website",
                    "start_url": "https://docs.example.com/",
                    "allowed_hosts": ["docs.example.com"],
                    "max_pages": 5,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        kb_id = created.json()["id"]
        started = client.post(
            f"/api/admin/assistant/kb/{kb_id}/crawl/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(started.status_code, 202, started.content)

        def empty_http(url: str) -> RawHttpResponse:
            return RawHttpResponse(200, "text/html", b"<html></html>", url)

        run_website_crawl(started.json()["job"]["id"], http_get=empty_http)
        kb = AssistantKnowledgeBase.objects.get(pk=kb_id)
        self.assertEqual(kb.status, AssistantKnowledgeBase.STATUS_ERROR)
        status = client.get(f"/api/admin/assistant/kb/{kb_id}/crawl/")
        self.assertEqual(status.json()["job"]["status"], "failed")
        self.assertIn("www", status.json()["job"]["status_message"])
