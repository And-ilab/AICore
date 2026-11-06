"""INT-10 full load against the in-process Bitrix catalog."""

from __future__ import annotations

import os
import sys
from io import StringIO
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.test import TestCase, override_settings  # noqa: E402

from ingest.bitrix_client import (  # noqa: E402
    get_mock_bitrix_catalog_client,
    normalize_article,
    parse_list_payload,
    reset_mock_bitrix_catalog_client,
)
from ingest.full_load import run_full_load  # noqa: E402
from ingest.models import CCProductionChunk  # noqa: E402


BODY = "Комиссия за перевод между счетами составляет один процент."


def _article(**overrides):
    payload = {
        "article_id": 101,
        "iblock_id": 42,
        "version_id": 7,
        "title": "Комиссия за перевод",
        "body_plain": BODY,
        "permalink": "https://suz.local/articles/101",
        "status": "published",
        "locale": "ru",
        "visibility_scope": ["kc_operator"],
        "updated_at": "2026-05-27T14:32:01+03:00",
    }
    payload.update(overrides)
    return payload


@override_settings(
    SUZ_INGEST_MODE="mock",
    SUZ_ALLOWED_IBLOCK_IDS=frozenset(),
    BITRIX_REST_BASE_URL="",
)
class SuzFullLoadTest(TestCase):
    def setUp(self):
        reset_mock_bitrix_catalog_client()
        catalog = get_mock_bitrix_catalog_client()
        catalog.seed_page(42, 0, [101, 102])
        catalog.seed_article(42, 101, _article())
        catalog.seed_article(
            42,
            102,
            _article(
                article_id=102,
                version_id=8,
                title="Без ссылки",
                permalink="",
            ),
        )

    def test_indexes_published_article_and_reports_missing_permalink(self):
        first = run_full_load(iblock_id=42)
        first_count = CCProductionChunk.objects.filter(article_id=101).count()

        self.assertEqual(first.indexed, 1)
        self.assertEqual(first.errors, 1)
        self.assertEqual(first.failures[0].article_id, 102)
        self.assertIn("permalink", first.failures[0].error)
        self.assertGreater(first_count, 0)
        self.assertFalse(
            CCProductionChunk.objects.filter(article_id=102).exists()
        )

        second = run_full_load(iblock_id=42)
        self.assertEqual(second.indexed, 0)
        self.assertEqual(second.unchanged, 1)
        self.assertEqual(second.errors, 1)
        self.assertEqual(
            CCProductionChunk.objects.filter(article_id=101).count(),
            first_count,
        )

    def test_non_numeric_version_id_is_an_article_error(self):
        catalog = get_mock_bitrix_catalog_client()
        catalog.seed_page(42, 0, [103])
        catalog.seed_article(
            42,
            103,
            _article(article_id=103, version_id="hist-92831"),
        )

        result = run_full_load(iblock_id=42, limit=1)
        # Page is still the original seed of 101, 102 unless replaced.
        # seed_page overwrites start 0, so only 103 is listed.
        self.assertEqual(result.errors, 1)
        self.assertEqual(result.failures[0].article_id, 103)
        self.assertFalse(
            CCProductionChunk.objects.filter(article_id=103).exists()
        )

    def test_missing_article_hard_deletes_existing_chunks(self):
        catalog = get_mock_bitrix_catalog_client()
        catalog.seed_page(42, 0, [101])
        run_full_load(iblock_id=42)
        self.assertGreater(
            CCProductionChunk.objects.filter(article_id=101).count(),
            0,
        )

        catalog.mark_missing(42, 101)
        result = run_full_load(iblock_id=42)
        self.assertEqual(result.deleted, 1)
        self.assertFalse(
            CCProductionChunk.objects.filter(article_id=101).exists()
        )

    def test_dry_run_lists_ids_without_indexing(self):
        output = StringIO()
        call_command(
            "suz_full_load",
            "--iblock-id",
            "42",
            "--dry-run",
            stdout=output,
        )
        text = output.getvalue()
        self.assertIn("ids: 101, 102", text)
        self.assertFalse(CCProductionChunk.objects.exists())

    def test_parse_bitrix_rest_list_and_raw_element(self):
        page = parse_list_payload(
            {"result": [{"ID": "15"}, 16], "next": "50"}
        )
        self.assertEqual(page.article_ids, [15, 16])
        self.assertEqual(page.next_start, 50)

        article = normalize_article(
            {
                "result": {
                    "ID": "15",
                    "IBLOCK_ID": "42",
                    "NAME": "Тариф",
                    "DETAIL_TEXT": "Текст тарифа для оператора",
                    "DETAIL_PAGE_URL": "https://suz.local/15",
                    "ACTIVE": "Y",
                }
            },
            iblock_id=42,
            article_id=15,
        )
        self.assertEqual(article.title, "Тариф")
        self.assertEqual(article.permalink, "https://suz.local/15")
        self.assertEqual(article.status, "published")
        self.assertTrue(article.apply_default_scope)
        self.assertIsNone(article.visibility_scope)
