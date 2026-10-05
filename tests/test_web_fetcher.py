import os
import sys
from pathlib import Path
from unittest import TestCase

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

from ingest.web_fetcher import (  # noqa: E402
    OffHostRedirectError,
    RawHttpResponse,
    SsrfError,
    WhitelistError,
    canonicalize_url,
    crawl_website,
    host_in_whitelist,
    url_topic_priority,
    validate_fetch_url,
    validate_redirect,
)


class WebFetcherSecurityTest(TestCase):
    def test_ssrf_blocks_localhost_private_and_metadata(self):
        for url in (
            "http://127.0.0.1/",
            "http://localhost/admin",
            "http://10.1.2.3/secret",
            "http://169.254.169.254/latest/meta-data",
            "file:///etc/passwd",
        ):
            with self.assertRaises(SsrfError):
                validate_fetch_url(url, allowed_hosts=["example.com"], require_whitelist=False)

    def test_empty_whitelist_and_foreign_host_rejected(self):
        with self.assertRaises(WhitelistError):
            validate_fetch_url(
                "https://example.com/",
                allowed_hosts=[],
                check_dns=False,
            )
        with self.assertRaises(WhitelistError):
            validate_fetch_url(
                "https://evil.example/",
                allowed_hosts=["docs.example.com"],
                check_dns=False,
            )
        self.assertTrue(host_in_whitelist("www.docs.example.com", ["docs.example.com"]))
        self.assertTrue(host_in_whitelist("docs.example.com", ["www.docs.example.com"]))
        self.assertFalse(host_in_whitelist("blog.example.com", ["docs.example.com"]))
        self.assertFalse(host_in_whitelist("evil.example.com", ["www.docs.example.com"]))

    def test_same_host_redirect_ok_off_host_stops(self):
        validate_redirect(
            "https://docs.example.com/a",
            "https://docs.example.com/b",
            check_dns=False,
        )
        validate_redirect(
            "https://www.docs.example.com/",
            "https://docs.example.com/",
            check_dns=False,
        )
        with self.assertRaises(OffHostRedirectError):
            validate_redirect(
                "https://docs.example.com/a",
                "https://evil.example/b",
                check_dns=False,
            )
        with self.assertRaises(OffHostRedirectError):
            validate_redirect(
                "https://docs.example.com/a",
                "https://blog.example.com/b",
                check_dns=False,
            )

    def _http(self, mapping):
        def getter(url: str) -> RawHttpResponse:
            if url not in mapping:
                return RawHttpResponse(404, "text/plain", b"missing", url)
            status, ctype, body = mapping[url]
            return RawHttpResponse(status, ctype, body, url)
        return getter

    def test_robots_disallow_and_ignore(self):
        pages = {
            "https://docs.example.com/robots.txt": (
                200,
                "text/plain",
                b"User-agent: *\nDisallow: /secret\n",
            ),
            "https://docs.example.com/sitemap.xml": (404, "text/plain", b""),
            "https://docs.example.com/": (
                200,
                "text/html",
                b"<html><title>Home</title><a href='/secret'>x</a></html>",
            ),
            "https://docs.example.com/secret": (
                200,
                "text/html",
                b"<html><title>Secret</title><p>hidden</p></html>",
            ),
        }
        blocked = crawl_website(
            "https://docs.example.com/",
            allowed_hosts=["docs.example.com"],
            depth=2,
            max_pages=10,
            http_get=self._http(pages),
        )
        self.assertTrue(any(item.skipped_reason == "robots" for item in blocked))
        ignored = crawl_website(
            "https://docs.example.com/",
            allowed_hosts=["docs.example.com"],
            depth=2,
            max_pages=10,
            ignore_robots=True,
            http_get=self._http(pages),
        )
        self.assertTrue(any(item.url.endswith("/secret") and item.text for item in ignored))

    def test_canonicalize_encodes_cyrillic_query(self):
        url = canonicalize_url(
            "https://docs.example.com/вклады/?set_filter=Показать"
        )
        self.assertTrue(url.isascii())
        self.assertIn("set_filter=", url)
        self.assertNotIn("Показать", url)
        self.assertNotIn("вклады", url)

    def test_sitemap_index_yields_pages_not_xml_files(self):
        pages = {
            "https://docs.example.com/robots.txt": (200, "text/plain", b""),
            "https://docs.example.com/sitemap.xml": (
                200,
                "application/xml",
                b"<?xml version='1.0'?><sitemapindex>"
                b"<sitemap><loc>https://docs.example.com/sitemap-iblock-13.xml</loc></sitemap>"
                b"</sitemapindex>",
            ),
            "https://docs.example.com/sitemap-iblock-13.xml": (
                200,
                "application/xml",
                b"<?xml version='1.0'?><urlset>"
                b"<url><loc>https://docs.example.com/credits</loc></url>"
                b"</urlset>",
            ),
            "https://docs.example.com/": (
                200,
                "text/html",
                b"<html><title>Home</title><p>bank</p></html>",
            ),
            "https://docs.example.com/credits": (
                200,
                "text/html",
                b"<html><title>Credits</title><p>credit offer</p></html>",
            ),
        }
        fetched = crawl_website(
            "https://docs.example.com/",
            allowed_hosts=["docs.example.com"],
            depth=0,
            max_pages=5,
            http_get=self._http(pages),
        )
        urls = [item.final_url or item.url for item in fetched if item.text]
        self.assertTrue(any(url.rstrip("/").endswith("credits") for url in urls))
        self.assertFalse(any("sitemap" in url for url in urls))

    def test_sitemap_prefers_contacts_over_news(self):
        self.assertLess(
            url_topic_priority("https://docs.example.com/ru/kontakty"),
            url_topic_priority("https://docs.example.com/news/1"),
        )
        pages = {
            "https://docs.example.com/robots.txt": (200, "text/plain", b""),
            "https://docs.example.com/sitemap.xml": (
                200,
                "application/xml",
                b"<?xml version='1.0'?><urlset>"
                b"<url><loc>https://docs.example.com/news/1</loc></url>"
                b"<url><loc>https://docs.example.com/ru/kontakty</loc></url>"
                b"</urlset>",
            ),
            "https://docs.example.com/": (
                200,
                "text/html",
                b"<html><title>Home</title><p>bank</p></html>",
            ),
            "https://docs.example.com/news/1": (
                200,
                "text/html",
                b"<html><title>News</title><p>rate change</p></html>",
            ),
            "https://docs.example.com/ru/kontakty": (
                200,
                "text/html",
                b"<html><title>Contacts</title><p>+375 17 218 84 31 147</p></html>",
            ),
        }
        fetched = crawl_website(
            "https://docs.example.com/",
            allowed_hosts=["docs.example.com"],
            depth=0,
            max_pages=2,
            http_get=self._http(pages),
        )
        urls = [item.final_url or item.url for item in fetched if item.text]
        self.assertTrue(any("kontakty" in url for url in urls))
        self.assertFalse(any("/news/" in url for url in urls))

    def test_crawl_skips_broken_page_and_continues(self):
        def getter(url: str) -> RawHttpResponse:
            if url.endswith("/bad"):
                raise UnicodeEncodeError("ascii", "x", 0, 1, "boom")
            if url.endswith("robots.txt") or url.endswith("sitemap.xml"):
                return RawHttpResponse(404, "text/plain", b"", url)
            return RawHttpResponse(
                200,
                "text/html",
                b"<html><title>Home</title><p>ok</p><a href='/bad'>bad</a></html>",
                url,
            )

        pages = crawl_website(
            "https://docs.example.com/",
            allowed_hosts=["docs.example.com"],
            depth=1,
            max_pages=5,
            http_get=getter,
        )
        self.assertTrue(any(item.text and "ok" in item.text for item in pages))
        self.assertTrue(any(item.skipped_reason == "fetch_error" for item in pages))
