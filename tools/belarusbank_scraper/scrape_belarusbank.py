#!/usr/bin/env python3
"""Scrape public articles from belarusbank.by into topic-sorted UTF-8 .txt files.

Usage (from repo root):
  py -3 tools/belarusbank_scraper/scrape_belarusbank.py
  py -3 tools/belarusbank_scraper/scrape_belarusbank.py --workers 10 --skip-be

Output (default):
  local/kb/belarusbank/articles/<topic>/<subtopic>/<slug>.txt
  local/kb/belarusbank/manifest.jsonl
  local/kb/belarusbank/summary.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import threading
import time
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

BASE = "https://belarusbank.by"
SITEMAP_INDEX = f"{BASE}/sitemap.xml"
USER_AGENT = (
    "SuflerKBDevScraper/1.0 (+local knowledge-base seeding; contact: dev)"
)
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

TOPIC_LABELS = {
    "fizicheskim_licam": "Физическим лицам",
    "o-banke": "О банке",
    "docs": "Документы",
    "business": "Бизнесу",
    "be": "Беларуская версия",
    "other": "Прочее",
}

SUBTOPIC_LABELS = {
    "cards": "Карты",
    "credits": "Кредиты",
    "kredit": "Кредиты",
    "vklady": "Вклады",
    "deposits": "Вклады",
    "investicii": "Инвестиции",
    "online": "Онлайн-сервисы",
    "online_services": "Онлайн-сервисы",
    "payments": "Платежи",
    "insurance": "Страхование",
    "rassrochka": "Рассрочка",
    "perevody": "Переводы",
    "bankovskie-perevody": "Банковские переводы",
    "bank-segodnya": "Банк сегодня",
    "press-centr": "Пресс-центр",
    "novosti": "Новости",
    "biznesu": "Документы для бизнеса",
    "fizicheskim": "Документы для физлиц",
    "otdeleniya": "Отделения",
    "acquiring": "Эквайринг",
    "create-business": "Открытие бизнеса",
    "credit": "Кредиты для бизнеса",
}


@dataclass
class Article:
    url: str
    title: str
    topic: str
    topic_label: str
    subtopic: str
    subtopic_label: str
    text: str
    path: str
    chars: int
    status: str
    error: str = ""


class _TextExtractor(HTMLParser):
    """Collect visible text from selected root containers."""

    SKIP_TAGS = {"script", "style", "noscript", "svg", "iframe", "nav", "footer"}
    VOID = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }
    INTERESTING_CLASSES = {
        "bx-catalog-element",
        "news-detail",
        "detail-text",
        "page-content",
        "bx-content",
        "article-detail",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._capture_roots = 0
        self._node_depth_in_capture = 0
        self._skip_depth = 0
        self._chunks: list[str] = []
        self._banner_title = ""
        self._in_banner_title = False
        self._in_h1 = False
        self._h1 = ""

    def _interesting(self, tag: str, classes: set[str]) -> bool:
        if classes & self.INTERESTING_CLASSES:
            return True
        if tag == "article":
            return True
        # Product pages use section.bx-text; service/news pages use div.bx-text.
        if "bx-text" in classes and not any("cookie" in c for c in classes):
            return True
        return False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = {k: (v or "") for k, v in attrs}
        classes = set(attrs_d.get("class", "").split())

        if tag == "title":
            self._in_title = True
        if tag == "h1":
            self._in_h1 = True
        if "detail-banner__title" in classes:
            self._in_banner_title = True

        if self._skip_depth:
            if tag not in self.VOID:
                self._skip_depth += 1
            return
        if tag in self.SKIP_TAGS:
            self._skip_depth = 1
            return

        entering = self._interesting(tag, classes)
        if entering:
            self._capture_roots += 1

        if self._capture_roots:
            if tag not in self.VOID:
                self._node_depth_in_capture += 1
            if tag in {"p", "li", "h1", "h2", "h3", "h4", "br", "tr"}:
                self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag == "h1":
            self._in_h1 = False
        if self._in_banner_title and tag in {"p", "div", "span"}:
            self._in_banner_title = False

        if self._skip_depth:
            self._skip_depth = max(0, self._skip_depth - 1)
            return

        if self._capture_roots:
            if tag in {"p", "li", "h1", "h2", "h3", "h4", "tr"}:
                self._chunks.append("\n")
            if tag not in self.VOID and self._node_depth_in_capture > 0:
                self._node_depth_in_capture -= 1
                # When leaving the outermost capture root, drop one root.
                if self._node_depth_in_capture == 0:
                    self._capture_roots = max(0, self._capture_roots - 1)

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title += text + " "
        if self._in_h1:
            self._h1 += text + " "
        if self._in_banner_title:
            self._banner_title += text + " "
        if self._capture_roots and not self._skip_depth:
            self._chunks.append(text + " ")

    def result_title(self) -> str:
        for candidate in (self._banner_title, self._h1, self.title):
            cleaned = _clean_space(candidate)
            if cleaned:
                cleaned = re.sub(
                    r"\s*[—\-–]\s*Беларусбанк.*$",
                    "",
                    cleaned,
                    flags=re.I,
                )
                return cleaned
        return ""

    def result_text(self) -> str:
        raw = "".join(self._chunks)
        raw = raw.replace("\xa0", " ")
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _fetch(url: str, timeout: float = 45.0, retries: int = 3) -> bytes:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "ru-RU,ru;q=0.9",
                },
            )
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except HTTPError as exc:
            # Do not retry permanent client errors except rate limits.
            if exc.code in {429, 500, 502, 503, 504} and attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
                last_exc = exc
                continue
            raise
        except (URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt + 1 < retries:
                time.sleep(1.2 * (attempt + 1))
                continue
            raise
    assert last_exc is not None
    raise last_exc


def _parse_sitemap_locs(xml_bytes: bytes) -> list[str]:
    root = ET.fromstring(xml_bytes)
    locs = [el.text.strip() for el in root.findall(".//sm:loc", NS) if el.text]
    if locs:
        return locs
    # Fallback without namespaces
    return [
        el.text.strip()
        for el in root.iter()
        if el.tag.endswith("loc") and el.text
    ]


def collect_urls(cache_dir: Path, refresh: bool = False) -> list[str]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    index_path = cache_dir / "sitemap.xml"
    if refresh or not index_path.exists():
        index_path.write_bytes(_fetch(SITEMAP_INDEX))
    child_urls = _parse_sitemap_locs(index_path.read_bytes())
    page_urls: list[str] = []
    for child in child_urls:
        name = Path(urlparse(child).path).name or "child.xml"
        path = cache_dir / name
        if refresh or not path.exists():
            path.write_bytes(_fetch(child))
        page_urls.extend(_parse_sitemap_locs(path.read_bytes()))
    # Prefer https belarusbank.by pages only
    cleaned: list[str] = []
    seen: set[str] = set()
    for url in page_urls:
        url = url.strip()
        if not url.startswith(BASE):
            continue
        if url in seen:
            continue
        seen.add(url)
        cleaned.append(url)
    return cleaned


def classify(url: str) -> tuple[str, str, str, str, str]:
    parts = [p for p in urlparse(url).path.strip("/").split("/") if p]
    if parts and parts[0] == "be":
        topic = "be"
        sub = parts[1] if len(parts) > 1 else "root"
        slug_parts = parts[2:] or parts[1:] or ["index"]
    elif parts:
        topic = parts[0] if parts[0] in TOPIC_LABELS else "other"
        if topic == "other":
            topic = parts[0]
            TOPIC_LABELS.setdefault(topic, topic)
        sub = parts[1] if len(parts) > 1 else "root"
        slug_parts = parts[2:] or ([parts[1]] if len(parts) > 1 else ["index"])
    else:
        topic, sub, slug_parts = "other", "root", ["home"]

    slug = "_".join(slug_parts).strip("_") or "index"
    slug = re.sub(r"[^\w\-]+", "_", slug, flags=re.U)[:120]
    topic_label = TOPIC_LABELS.get(topic, topic)
    sub_label = SUBTOPIC_LABELS.get(sub, sub.replace("-", " ").replace("_", " "))
    return topic, topic_label, sub, sub_label, slug


_CHROME_PATTERNS = [
    r"Выключить режим для слабовидящих.*?(?=Преимущества|Описание|TITLE:|\Z)",
    r"Размер шрифта.*?Цветовая схема.*?(?:Светло-синяя|Темная)",
    r"Курсы валют Банк на карте.*?(?:Частным лицам|Бизнесу)",
    r"Поделиться\s+",
    r"Заказать онлайн\s+Заказать по телефону\s+",
    r"Cookie|cookie|файлы cookie",
    r"ОАО «АСБ Беларусбанк» использует на своем сайте.*?персонализированных рекомендаций\.?",
    r"Принять все\s+Отклонить(?:\s+Настройка обработки)?",
]


def _strip_chrome(text: str) -> str:
    cleaned = text
    for pattern in _CHROME_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.I | re.S)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def extract_article(html: str, url: str) -> tuple[str, str]:
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass
    title = parser.result_title()
    text = parser.result_text()

    # Fallback: strip tags roughly if containers were empty
    if len(text) < 200:
        stripped = re.sub(
            r"(?is)<(script|style|noscript|svg).*?>.*?</\1>",
            " ",
            html,
        )
        stripped = re.sub(r"(?is)<!--.*?-->", " ", stripped)
        stripped = re.sub(r"(?is)<br\s*/?>", "\n", stripped)
        stripped = re.sub(r"(?is)</p>", "\n", stripped)
        stripped = re.sub(r"(?is)<[^>]+>", " ", stripped)
        stripped = _clean_space(stripped)
        if len(stripped) > len(text):
            text = stripped[:80000]

    text = _strip_chrome(text)
    if not title:
        _, _, _, _, slug = classify(url)
        title = slug.replace("_", " ")
    return title, text


def article_to_txt(article: Article) -> str:
    return (
        f"TITLE: {article.title}\n"
        f"URL: {article.url}\n"
        f"TOPIC: {article.topic_label} / {article.subtopic_label}\n"
        f"TOPIC_ID: {article.topic}/{article.subtopic}\n"
        f"SOURCE: belarusbank.by\n"
        f"{'=' * 60}\n\n"
        f"{article.text}\n"
    )


def url_fingerprint(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


TERMINAL_STATUSES = {"ok", "skipped_short", "http_error"}


class Manifest:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.done: set[str] = set()
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    status = row.get("status")
                    url = row.get("url")
                    # Retry only transient network failures on resume.
                    if url and status in TERMINAL_STATUSES:
                        self.done.add(url)

    def append(self, article: Article) -> None:
        with self.lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(article), ensure_ascii=False) + "\n")
            if article.status in TERMINAL_STATUSES:
                self.done.add(article.url)


def scrape_one(
    url: str,
    out_root: Path,
    min_chars: int,
) -> Article:
    topic, topic_label, sub, sub_label, slug = classify(url)
    rel_dir = Path(topic) / sub
    fname = f"{slug}__{url_fingerprint(url)}.txt"
    out_path = out_root / rel_dir / fname
    try:
        raw = _fetch(url)
        html = raw.decode("utf-8", errors="replace")
        title, text = extract_article(html, url)
        if len(text) < min_chars:
            return Article(
                url=url,
                title=title,
                topic=topic,
                topic_label=topic_label,
                subtopic=sub,
                subtopic_label=sub_label,
                text=text,
                path=str(out_path.relative_to(out_root.parent)),
                chars=len(text),
                status="skipped_short",
                error=f"text<{min_chars}",
            )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        article = Article(
            url=url,
            title=title,
            topic=topic,
            topic_label=topic_label,
            subtopic=sub,
            subtopic_label=sub_label,
            text=text,
            path=str(out_path.relative_to(out_root.parent)),
            chars=len(text),
            status="ok",
        )
        out_path.write_text(article_to_txt(article), encoding="utf-8")
        return article
    except HTTPError as exc:
        return Article(
            url=url,
            title="",
            topic=topic,
            topic_label=topic_label,
            subtopic=sub,
            subtopic_label=sub_label,
            text="",
            path="",
            chars=0,
            status="http_error",
            error=f"{exc.code}",
        )
    except (URLError, TimeoutError, OSError) as exc:
        return Article(
            url=url,
            title="",
            topic=topic,
            topic_label=topic_label,
            subtopic=sub,
            subtopic_label=sub_label,
            text="",
            path="",
            chars=0,
            status="network_error",
            error=str(exc)[:200],
        )


def filter_urls(urls: Iterable[str], skip_be: bool, skip_otdeleniya: bool) -> list[str]:
    result: list[str] = []
    for url in urls:
        path = urlparse(url).path
        if skip_be and (path.startswith("/be/") or path == "/be"):
            continue
        if skip_otdeleniya and "/otdeleniya/" in path:
            continue
        result.append(url)
    return result


def write_summary(out_dir: Path, counts: Counter[str], topic_ok: Counter[str]) -> None:
    summary = {
        "source": BASE,
        "output": str(out_dir / "articles"),
        "status_counts": dict(counts),
        "articles_by_topic": dict(topic_ok),
        "topic_labels": TOPIC_LABELS,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    default_out = repo / "local" / "kb" / "belarusbank"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=default_out)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="0 = all")
    parser.add_argument("--min-chars", type=int, default=180)
    parser.add_argument("--refresh-sitemaps", action="store_true")
    parser.add_argument("--skip-be", action="store_true", default=True)
    parser.add_argument("--include-be", action="store_true")
    parser.add_argument(
        "--skip-otdeleniya",
        action="store_true",
        default=True,
        help="Skip branch office address cards (default on)",
    )
    parser.add_argument("--include-otdeleniya", action="store_true")
    parser.add_argument("--resume", action="store_true", default=True)
    args = parser.parse_args()

    skip_be = not args.include_be if args.include_be else args.skip_be
    skip_otdeleniya = (
        not args.include_otdeleniya if args.include_otdeleniya else args.skip_otdeleniya
    )

    out_dir: Path = args.out
    articles_dir = out_dir / "articles"
    cache_dir = out_dir / "_raw_sitemaps"
    articles_dir.mkdir(parents=True, exist_ok=True)

    print(f"Collecting sitemap URLs -> {cache_dir}")
    urls = collect_urls(cache_dir, refresh=args.refresh_sitemaps)
    urls = filter_urls(urls, skip_be=skip_be, skip_otdeleniya=skip_otdeleniya)

    def _priority(url: str) -> tuple[int, str]:
        path = urlparse(url).path
        if path.startswith("/fizicheskim_licam/"):
            return (0, url)
        if path.startswith("/docs/"):
            return (1, url)
        if path.startswith("/business/"):
            return (2, url)
        if path.startswith("/o-banke/"):
            return (3, url)
        return (4, url)

    urls.sort(key=_priority)
    if args.limit > 0:
        urls = urls[: args.limit]

    manifest = Manifest(out_dir / "manifest.jsonl")
    pending = [u for u in urls if u not in manifest.done] if args.resume else urls
    print(
        f"URLs total={len(urls)} pending={len(pending)} "
        f"done={len(manifest.done)} workers={args.workers}"
    )
    print(f"Output: {articles_dir}")

    counts: Counter[str] = Counter()
    topic_ok: Counter[str] = Counter()
    # Seed counters from existing manifest for resume summary
    if manifest.path.exists():
        with manifest.path.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                counts[row.get("status", "unknown")] += 1
                if row.get("status") == "ok":
                    topic_ok[row.get("topic_label") or row.get("topic") or "?"] += 1

    lock = threading.Lock()
    started = time.time()
    processed = 0

    def _handle(article: Article) -> None:
        nonlocal processed
        manifest.append(article)
        with lock:
            counts[article.status] += 1
            if article.status == "ok":
                topic_ok[article.topic_label] += 1
            processed += 1
            if processed % 25 == 0 or processed == len(pending):
                elapsed = max(time.time() - started, 0.1)
                rate = processed / elapsed
                print(
                    f"[{processed}/{len(pending)}] "
                    f"ok={counts['ok']} short={counts['skipped_short']} "
                    f"err={counts['http_error'] + counts['network_error']} "
                    f"{rate:.1f} pages/s",
                    flush=True,
                )

    if not pending:
        print("Nothing to do (all URLs already in manifest).")
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [
                pool.submit(scrape_one, url, articles_dir, args.min_chars)
                for url in pending
            ]
            for fut in concurrent.futures.as_completed(futures):
                _handle(fut.result())

    write_summary(out_dir, counts, topic_ok)
    print("\nDone.")
    print(json.dumps({"status_counts": dict(counts), "by_topic": dict(topic_ok)}, ensure_ascii=False, indent=2))
    print(f"Articles dir: {articles_dir}")
    print(f"Summary: {out_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
