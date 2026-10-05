"""Shared website fetch core (SSRF, whitelist, robots). Admin crawl only — not chat."""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Callable, Iterable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)
USER_AGENT = "SuflerHubBot/1.0 (+https://belarusbank.by)"
READ_TIMEOUT = 15
MAX_BYTES = 5 * 1024 * 1024
DEFAULT_DEPTH = 1
DEFAULT_MAX_PAGES = 15
ALLOWED_SCHEMES = frozenset({"http", "https"})
BLOCKED_HOSTS = frozenset({
    "localhost", "localhost.localdomain", "metadata",
    "metadata.google.internal", "metadata.goog", "ip6-localhost", "ip6-loopback",
})
TWO_LEVEL_PUBLIC_SUFFIXES = frozenset({
    ("co", "uk"), ("ac", "uk"), ("gov", "uk"), ("com", "au"), ("net", "au"),
    ("org", "au"), ("com", "by"), ("gov", "by"), ("com", "ru"), ("net", "ru"),
    ("org", "ru"), ("co", "jp"), ("com", "br"),
})
HttpGet = Callable[[str], "RawHttpResponse"]


class FetcherError(Exception):
    def __init__(self, message: str, *, code: str = "fetcher_error") -> None:
        super().__init__(message)
        self.code = code


class SsrfError(FetcherError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="ssrf_blocked")


class WhitelistError(FetcherError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="host_not_allowed")


class OffHostRedirectError(FetcherError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="off_host_redirect")


@dataclass(frozen=True)
class RawHttpResponse:
    status: int
    content_type: str
    body: bytes
    final_url: str


@dataclass
class FetchedPage:
    url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    title: str = ""
    text: str = ""
    links: list[str] = field(default_factory=list)
    skipped_reason: str = ""


class _HTMLTextExtractor(HTMLParser):
    _SKIP = frozenset({"script", "style", "noscript", "svg", "template"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._parts: list[str] = []
        self._links: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name in self._SKIP:
            self._skip += 1
            return
        if name == "title":
            self._in_title = True
        if name == "a" and self._skip == 0:
            href = next((v.strip() for k, v in attrs if k.lower() == "href" and v), "")
            if href:
                self._links.append(href)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in self._SKIP and self._skip:
            self._skip -= 1
        if name == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title = (self.title + " " + text).strip()
            return
        self._parts.append(text)

    def extracted_text(self) -> str:
        return " ".join(self._parts)

    def extracted_links(self) -> list[str]:
        return list(self._links)


def registrable_domain(host: str) -> str:
    hostname = (host or "").split("%")[0].lower().rstrip(".")
    if hostname.startswith("[") and hostname.endswith("]"):
        return hostname
    parts = [part for part in hostname.split(".") if part]
    if len(parts) <= 2:
        return hostname
    if tuple(parts[-2:]) in TWO_LEVEL_PUBLIC_SUFFIXES and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def hostname_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower().rstrip(".")


def _idna_host(host: str) -> str:
    hostname = (host or "").lower().rstrip(".")
    if not hostname or hostname.isascii():
        return hostname
    try:
        return hostname.encode("idna").decode("ascii")
    except UnicodeError:
        return hostname


def _encode_path(path: str) -> str:
    value = path or "/"
    if value.isascii():
        return value
    return quote(value, safe="/%:@!$&'()*+,;=-._~", encoding="utf-8")


def _encode_query(query: str) -> str:
    if not query or query.isascii():
        return query
    return urlencode(parse_qsl(query, keep_blank_values=True), doseq=True, encoding="utf-8")


def canonicalize_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    scheme = (parsed.scheme or "").lower()
    host = _idna_host(parsed.hostname or "")
    if not scheme or not host:
        return (url or "").strip()
    port = parsed.port
    netloc = host
    if port and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    path = _encode_path(parsed.path or "/")
    query = _encode_query(parsed.query)
    return urlunparse((scheme, netloc, path, "", query, ""))


def normalize_allowed_hosts(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        values = [part.strip() for part in raw.replace(";", ",").split(",")]
    elif isinstance(raw, Sequence):
        values = [str(item).strip() for item in raw]
    else:
        return []
    seen: list[str] = []
    for item in values:
        host = item.lower().removeprefix("https://").removeprefix("http://")
        host = host.split("/")[0].split(":")[0].rstrip(".")
        if host and host not in seen:
            seen.append(host)
    return seen


def strip_www(host: str) -> str:
    hostname = (host or "").lower().rstrip(".")
    return hostname[4:] if hostname.startswith("www.") else hostname


def host_in_whitelist(host: str, allowed_hosts: Sequence[str]) -> bool:
    hostname = (host or "").lower().rstrip(".")
    if not hostname or not allowed_hosts:
        return False
    for entry in allowed_hosts:
        allowed = (entry or "").lower().rstrip(".")
        if not allowed:
            continue
        if hostname == allowed or hostname.endswith("." + allowed):
            return True
        # www.example.com ↔ example.com; sibling hosts stay blocked.
        if strip_www(hostname) and strip_www(hostname) == strip_www(allowed):
            return True
    return False


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _is_blocked_ip(ip.ipv4_mapped)
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return True
    if ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return True
    return bool(getattr(ip, "is_site_local", False))


def _parse_ip_literal(host: str):
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


def assert_public_http_url(url: str) -> None:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise SsrfError("разрешены только URL http/https")
    if parsed.username or parsed.password:
        raise SsrfError("URL с учётными данными запрещён")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise SsrfError("в URL нет хоста")
    if host in BLOCKED_HOSTS:
        raise SsrfError("хост запрещён политикой SSRF")
    literal = _parse_ip_literal(host)
    if literal is not None and _is_blocked_ip(literal):
        raise SsrfError("адрес назначения запрещён политикой SSRF")


def resolve_public_host(host: str) -> list[str]:
    hostname = (host or "").lower().rstrip(".")
    if not hostname:
        raise SsrfError("в URL нет хоста")
    if hostname in BLOCKED_HOSTS:
        raise SsrfError("хост запрещён политикой SSRF")
    literal = _parse_ip_literal(hostname)
    if literal is not None:
        if _is_blocked_ip(literal):
            raise SsrfError("адрес назначения запрещён политикой SSRF")
        return [str(literal)]
    try:
        answers = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SsrfError("не удалось разрешить хост") from exc
    ips: list[str] = []
    for item in answers:
        raw = item[4][0]
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            raise SsrfError("хост резолвится в запрещённый адрес")
        text = str(ip)
        if text not in ips:
            ips.append(text)
    if not ips:
        raise SsrfError("хост не резолвится в публичный адрес")
    return ips


def validate_fetch_url(
    url: str,
    *,
    allowed_hosts: Sequence[str],
    require_whitelist: bool = True,
    check_dns: bool = True,
) -> str:
    canonical = canonicalize_url(url)
    assert_public_http_url(canonical)
    host = hostname_of(canonical)
    if require_whitelist and not host_in_whitelist(host, allowed_hosts):
        raise WhitelistError("домен не входит в список разрешённых")
    if check_dns:
        resolve_public_host(host)
    return canonical


def validate_redirect(from_url: str, to_url: str, *, check_dns: bool = True) -> str:
    target = canonicalize_url(to_url)
    assert_public_http_url(target)
    from_host = hostname_of(from_url)
    to_host = hostname_of(target)
    # Same host or www ↔ apex. Sibling subdomains and other sites stay blocked.
    if from_host != to_host and strip_www(from_host) != strip_www(to_host):
        raise OffHostRedirectError("редирект на другой хост запрещён")
    if check_dns:
        resolve_public_host(hostname_of(target))
    return target


def same_registrable_domain(url: str, origin_url: str) -> bool:
    return registrable_domain(hostname_of(url)) == registrable_domain(
        hostname_of(origin_url)
    )


class _SameHostRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        validate_redirect(req.full_url, newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _decode_body(body: bytes, content_type: str) -> str:
    charset = "utf-8"
    lowered = (content_type or "").lower()
    if "charset=" in lowered:
        charset = lowered.split("charset=", 1)[1].split(";")[0].strip().strip("\"'")
    for encoding in (charset, "utf-8", "cp1251"):
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")


def extract_html(url: str, body: bytes, content_type: str) -> tuple[str, str, list[str]]:
    parser = _HTMLTextExtractor()
    try:
        parser.feed(_decode_body(body, content_type))
        parser.close()
    except Exception:
        text = _decode_body(body, content_type)
        return "", " ".join(text.split()), []
    links = [urljoin(url, href) for href in parser.extracted_links()]
    return parser.title[:500], parser.extracted_text(), links


_CONTACT_PATH_RE = re.compile(
    r"kontakt|contact|hotline|obratn|rekvizit|o-bank|about|ofis|office|address",
    re.IGNORECASE,
)


def is_sitemap_url(url: str) -> bool:
    """True for sitemap.xml / sitemap-iblock-13.xml — not a human page."""
    path = urlparse(url or "").path.lower()
    name = path.rsplit("/", 1)[-1]
    return "sitemap" in path and (
        name.endswith(".xml")
        or name.endswith(".xml.gz")
        or "sitemap" in name
    )


def url_topic_priority(url: str) -> int:
    """Lower is better: contacts/about before random sitemap news."""
    if is_sitemap_url(url):
        return 99
    path = unquote(urlparse(url or "").path)
    if _CONTACT_PATH_RE.search(path):
        return 0
    return 1


def parse_sitemap_urls(body: bytes) -> list[str]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    urls: list[str] = []
    for node in root.iter():
        tag = node.tag.split("}", 1)[-1].lower()
        if tag == "loc" and (node.text or "").strip():
            urls.append(node.text.strip())
    return urls


def _default_http_get(url: str) -> RawHttpResponse:
    validate_fetch_url(url, allowed_hosts=[], require_whitelist=False)
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        method="GET",
    )
    opener = build_opener(_SameHostRedirectHandler)
    try:
        with opener.open(request, timeout=READ_TIMEOUT) as response:
            raw = response.read(MAX_BYTES + 1)
            status = int(getattr(response, "status", 200) or 200)
            content_type = str(response.headers.get("Content-Type") or "")
            final_url = str(response.geturl() or url)
    except HTTPError as exc:
        raw = exc.read(MAX_BYTES + 1) if exc.fp else b""
        status = int(exc.code)
        content_type = str(exc.headers.get("Content-Type") or "") if exc.headers else ""
        final_url = str(exc.geturl() or url)
    except URLError as exc:
        raise FetcherError(f"не удалось загрузить страницу: {exc.reason}") from exc
    if len(raw) > MAX_BYTES:
        raise FetcherError("страница больше 5 МБ")
    logger.info(
        "web_fetch url=%s status=%s bytes=%s",
        canonicalize_url(final_url),
        status,
        len(raw),
    )
    return RawHttpResponse(
        status=status,
        content_type=content_type,
        body=raw,
        final_url=canonicalize_url(final_url),
    )


def _http_get(url: str, http_get: HttpGet | None) -> RawHttpResponse:
    return (http_get or _default_http_get)(url)


def load_robots(start_url: str, *, http_get: HttpGet | None = None) -> RobotFileParser:
    parsed = urlparse(canonicalize_url(start_url))
    robots_url = urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        response = _http_get(robots_url, http_get)
        if 200 <= response.status < 300:
            parser.parse(_decode_body(response.body, response.content_type).splitlines())
        else:
            parser.parse([])
    except FetcherError:
        parser.parse([])
    return parser


def load_sitemap_urls(
    start_url: str,
    *,
    http_get: HttpGet | None = None,
    page_limit: int = 200,
) -> list[str]:
    parsed = urlparse(canonicalize_url(start_url))
    sitemap_url = urlunparse((parsed.scheme, parsed.netloc, "/sitemap.xml", "", "", ""))
    try:
        response = _http_get(sitemap_url, http_get)
    except FetcherError:
        return []
    if not (200 <= response.status < 300):
        return []
    pending = deque(parse_sitemap_urls(response.body))
    pages: list[str] = []
    seen: set[str] = set()
    nested = 0
    while pending and len(pages) < max(1, int(page_limit)) and nested < 20:
        loc = pending.popleft()
        if loc in seen:
            continue
        seen.add(loc)
        if is_sitemap_url(loc):
            nested += 1
            try:
                child = _http_get(loc, http_get)
            except FetcherError:
                continue
            if 200 <= child.status < 300:
                pending.extend(parse_sitemap_urls(child.body))
            continue
        pages.append(loc)
    return pages


def is_html_content(content_type: str, url: str = "") -> bool:
    lowered = (content_type or "").split(";", 1)[0].strip().lower()
    if lowered in {"text/html", "application/xhtml+xml"}:
        return True
    path = urlparse(url).path.lower()
    if path.endswith((".pdf", ".docx", ".doc")):
        return False
    return lowered in {"", "text/plain"}


def is_pdf_content(content_type: str, url: str = "") -> bool:
    lowered = (content_type or "").split(";", 1)[0].strip().lower()
    return lowered == "application/pdf" or urlparse(url).path.lower().endswith(".pdf")


def is_docx_content(content_type: str, url: str = "") -> bool:
    lowered = (content_type or "").split(";", 1)[0].strip().lower()
    path = urlparse(url).path.lower()
    return "officedocument.wordprocessingml.document" in lowered or path.endswith(".docx")


def extract_page_payload(page: FetchedPage) -> FetchedPage:
    if is_html_content(page.content_type, page.final_url):
        title, text, links = extract_html(page.final_url, page.body, page.content_type)
        page.title = title
        page.text = text
        page.links = links
    return page


def robots_can_fetch(robots: RobotFileParser, url: str, *, ignore_robots: bool) -> bool:
    if ignore_robots:
        return True
    try:
        return bool(robots.can_fetch(USER_AGENT, url))
    except Exception:
        return True


def crawl_website(
    start_url: str,
    *,
    allowed_hosts: Sequence[str],
    depth: int = DEFAULT_DEPTH,
    max_pages: int = DEFAULT_MAX_PAGES,
    ignore_robots: bool = False,
    http_get: HttpGet | None = None,
    on_page: Callable[[FetchedPage], None] | None = None,
) -> list[FetchedPage]:
    hosts = normalize_allowed_hosts(allowed_hosts)
    if not hosts:
        raise WhitelistError("список разрешённых доменов пуст")
    origin = validate_fetch_url(
        start_url,
        allowed_hosts=hosts,
        check_dns=http_get is None,
    )
    robots = load_robots(origin, http_get=http_get)
    pending: deque[tuple[str, int]] = deque([(origin, 0)])
    limit = max(1, int(max_pages))
    sitemap_budget = max(limit * 2, limit)
    sitemap_pages: list[str] = []
    for sitemap_url in load_sitemap_urls(
        origin, http_get=http_get, page_limit=sitemap_budget
    ):
        if len(sitemap_pages) >= sitemap_budget:
            break
        try:
            canonical = canonicalize_url(sitemap_url)
            if is_sitemap_url(canonical):
                continue
            if same_registrable_domain(canonical, origin):
                sitemap_pages.append(canonical)
        except Exception:
            continue
    sitemap_pages.sort(key=url_topic_priority)
    for canonical in sitemap_pages:
        pending.append((canonical, 0))
    seen: set[str] = set()
    pages: list[FetchedPage] = []
    max_depth = max(0, int(depth))
    fetched_ok = 0
    attempt_limit = max(limit * 3, limit)

    while pending and fetched_ok < limit and len(pages) < attempt_limit:
        current, current_depth = pending.popleft()
        try:
            canonical = canonicalize_url(current)
        except Exception:
            continue
        if canonical in seen:
            continue
        if is_sitemap_url(canonical):
            continue
        seen.add(canonical)
        page = _crawl_one(
            canonical,
            origin=origin,
            hosts=hosts,
            robots=robots,
            ignore_robots=ignore_robots,
            http_get=http_get,
        )
        pages.append(page)
        if on_page is not None:
            try:
                on_page(page)
            except Exception:
                logger.exception("website crawl on_page failed url=%s", page.url)
        if page.skipped_reason:
            continue
        fetched_ok += 1
        if 200 <= page.status < 300 and current_depth < max_depth:
            for href in page.links:
                try:
                    child = canonicalize_url(href)
                except Exception:
                    continue
                if child in seen or not same_registrable_domain(child, origin):
                    continue
                if url_topic_priority(child) == 0:
                    pending.appendleft((child, current_depth + 1))
                else:
                    pending.append((child, current_depth + 1))
    return pages


def _crawl_one(
    canonical: str,
    *,
    origin: str,
    hosts: Sequence[str],
    robots: RobotFileParser,
    ignore_robots: bool,
    http_get: HttpGet | None,
) -> FetchedPage:
    empty = FetchedPage(
        url=canonical, final_url=canonical, status=0, content_type="", body=b""
    )
    try:
        assert_public_http_url(canonical)
        if not same_registrable_domain(canonical, origin):
            empty.skipped_reason = "off_domain"
            return empty
        if not host_in_whitelist(hostname_of(canonical), hosts):
            if not host_in_whitelist(registrable_domain(hostname_of(canonical)), hosts):
                empty.skipped_reason = "not_whitelisted"
                return empty
        if http_get is None:
            resolve_public_host(hostname_of(canonical))
        if not robots_can_fetch(robots, canonical, ignore_robots=ignore_robots):
            empty.skipped_reason = "robots"
            return empty
        response = _http_get(canonical, http_get)
    except OffHostRedirectError:
        empty.skipped_reason = "off_host_redirect"
        return empty
    except (SsrfError, WhitelistError, FetcherError) as exc:
        empty.skipped_reason = exc.code
        return empty
    except Exception as exc:
        logger.warning("skip page %s: %s", canonical, exc)
        empty.skipped_reason = "fetch_error"
        return empty
    page = FetchedPage(
        url=canonical,
        final_url=response.final_url,
        status=response.status,
        content_type=response.content_type,
        body=response.body,
    )
    if 200 <= response.status < 300:
        extract_page_payload(page)
    return page


def iter_html_and_document_pages(pages: Iterable[FetchedPage]) -> Iterable[FetchedPage]:
    for page in pages:
        if not page.skipped_reason:
            yield page
