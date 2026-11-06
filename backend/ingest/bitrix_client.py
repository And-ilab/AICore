"""Bitrix SUZ client: INT-09 /changes polling and INT-10 full load."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)


class BitrixClientError(RuntimeError):
    """Bitrix REST / changes API failure."""


class RetryableBitrixError(BitrixClientError):
    """HTTP 5xx or a network failure. Safe to retry."""


class BitrixAuthError(BitrixClientError):
    """401/403 from Bitrix. The full load must stop."""

    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        super().__init__(detail)


class ArticleNotFound(BitrixClientError):
    """404 on one article card (INT-06)."""

    def __init__(self, article_id: int) -> None:
        self.article_id = article_id
        super().__init__(f"Bitrix article {article_id} was not found")


@dataclass
class ChangesPage:
    cursor: str
    events: list[dict[str, Any]]


class BitrixChangesClient(Protocol):
    def fetch_changes(self, since: str, *, limit: int = 100) -> ChangesPage: ...


@dataclass
class MockBitrixChangesClient:
    """In-process stand-in used when SUZ_INGEST_MODE=mock (local INT-T)."""

    pages: dict[str, ChangesPage] = field(default_factory=dict)
    default_page: ChangesPage | None = None

    def seed(self, since: str, events: list[Mapping[str, Any]], cursor: str) -> None:
        self.pages[since] = ChangesPage(
            cursor=cursor,
            events=[dict(item) for item in events],
        )

    def fetch_changes(self, since: str, *, limit: int = 100) -> ChangesPage:
        page = self.pages.get(since) or self.default_page
        if page is None:
            page = ChangesPage(cursor=since or _utcnow_iso(), events=[])
        else:
            page = ChangesPage(
                cursor=page.cursor,
                events=list(page.events)[:limit],
            )
        _log_bitrix_response(mode="mock", status=200, body=page)
        return page


@dataclass
class HttpBitrixChangesClient:
    """Production Model B fallback: GET …/changes?since=&limit= (INT-09)."""

    base_url: str
    service_token: str
    changes_path: str
    timeout_seconds: float = 15.0

    def fetch_changes(self, since: str, *, limit: int = 100) -> ChangesPage:
        if not self.base_url:
            raise BitrixClientError("BITRIX_REST_BASE_URL is not configured")
        if not self.service_token:
            raise BitrixClientError("BITRIX_SERVICE_TOKEN is not configured")

        query = urlencode({"since": since, "limit": min(max(limit, 1), 100)})
        path = self.changes_path.lstrip("/")
        url = urljoin(self.base_url.rstrip("/") + "/", f"{path}?{query}")
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {self.service_token}",
                "Accept": "application/json",
                "User-Agent": "sufler-ingest-reconcile/1.0",
            },
            method="GET",
        )
        status: int | None = None
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                status = getattr(response, "status", None)
                raw = response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.error(
                "bitrix_response mode=http status=%s body=%s",
                exc.code,
                body,
            )
            raise BitrixClientError(
                f"Bitrix changes HTTP {exc.code}: {body[:300]}"
            ) from exc
        except URLError as exc:
            logger.exception("bitrix_response_failed mode=http")
            raise BitrixClientError(f"Bitrix changes unreachable: {exc}") from exc

        decoded = raw.decode("utf-8", errors="replace")
        try:
            payload = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.error(
                "bitrix_response mode=http status=%s body=%s",
                status,
                decoded,
            )
            raise BitrixClientError("Bitrix changes returned invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise BitrixClientError("Bitrix changes root must be an object")

        cursor = str(payload.get("cursor") or since or _utcnow_iso())
        events_raw = payload.get("events") or []
        if not isinstance(events_raw, list):
            raise BitrixClientError("Bitrix changes.events must be a list")
        events = [dict(item) for item in events_raw if isinstance(item, Mapping)]
        page = ChangesPage(cursor=cursor, events=events[:limit])
        _log_bitrix_response(mode="http", status=status, body=payload)
        return page


def _log_bitrix_response(*, mode: str, status: Any, body: Any) -> None:
    if isinstance(body, ChangesPage):
        payload = {"cursor": body.cursor, "events": body.events}
    else:
        payload = body
    logger.info(
        "bitrix_response mode=%s status=%s body=%s",
        mode,
        status,
        json.dumps(payload, ensure_ascii=False, default=str),
    )


_MOCK_CLIENT = MockBitrixChangesClient()


def reset_mock_bitrix_client() -> MockBitrixChangesClient:
    global _MOCK_CLIENT
    _MOCK_CLIENT = MockBitrixChangesClient()
    return _MOCK_CLIENT


def get_mock_bitrix_client() -> MockBitrixChangesClient:
    return _MOCK_CLIENT


def ingest_mode() -> str:
    mode = str(getattr(settings, "SUZ_INGEST_MODE", "mock") or "mock").strip().lower()
    return mode if mode in {"mock", "prod"} else "mock"


def get_bitrix_changes_client() -> BitrixChangesClient:
    if ingest_mode() == "mock" or not getattr(settings, "BITRIX_REST_BASE_URL", ""):
        return _MOCK_CLIENT
    return HttpBitrixChangesClient(
        base_url=str(settings.BITRIX_REST_BASE_URL),
        service_token=str(getattr(settings, "BITRIX_SERVICE_TOKEN", "") or ""),
        changes_path=str(
            getattr(settings, "BITRIX_CHANGES_PATH", "/local/api/sufler/v1/changes")
        ),
        timeout_seconds=float(
            getattr(settings, "BITRIX_HTTP_TIMEOUT_SECONDS", 15.0)
        ),
    )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ArticleListPage:
    article_ids: list[int]
    next_start: int | None


@dataclass
class NormalizedArticle:
    """Article card reduced to the fields INT-10 can index."""

    article_id: int
    iblock_id: int
    version_id: Any
    version_number: int | None
    title: str
    preview: str
    body_html: str
    body_plain: str
    permalink: str
    locale: str
    visibility_scope: tuple[str, ...] | None
    status: str | None
    section_id: int | None
    updated_at: str | None
    apply_default_scope: bool


class BitrixCatalogClient(Protocol):
    def list_articles(self, iblock_id: int, *, start: int) -> ArticleListPage: ...

    def get_article(self, iblock_id: int, article_id: int) -> NormalizedArticle: ...


@dataclass
class MockBitrixCatalogClient:
    """In-process catalog used when SUZ_INGEST_MODE=mock or base URL is empty."""

    pages: dict[tuple[int, int], ArticleListPage] = field(default_factory=dict)
    articles: dict[tuple[int, int], dict[str, Any]] = field(default_factory=dict)
    missing: set[tuple[int, int]] = field(default_factory=set)

    def seed_page(
        self,
        iblock_id: int,
        start: int,
        article_ids: list[int],
        next_start: int | None = None,
    ) -> None:
        self.pages[(iblock_id, start)] = ArticleListPage(
            article_ids=list(article_ids),
            next_start=next_start,
        )

    def seed_article(
        self,
        iblock_id: int,
        article_id: int,
        payload: Mapping[str, Any],
    ) -> None:
        self.articles[(iblock_id, article_id)] = dict(payload)

    def mark_missing(self, iblock_id: int, article_id: int) -> None:
        self.missing.add((iblock_id, article_id))

    def list_articles(self, iblock_id: int, *, start: int) -> ArticleListPage:
        page = self.pages.get((iblock_id, start))
        if page is None:
            page = ArticleListPage(article_ids=[], next_start=None)
        _log_bitrix_response(
            mode="mock",
            status=200,
            body={"start": start, "ids": page.article_ids, "next": page.next_start},
        )
        return page

    def get_article(self, iblock_id: int, article_id: int) -> NormalizedArticle:
        key = (iblock_id, article_id)
        if key in self.missing or key not in self.articles:
            raise ArticleNotFound(article_id)
        article = normalize_article(
            self.articles[key],
            iblock_id=iblock_id,
            article_id=article_id,
        )
        _log_bitrix_response(
            mode="mock",
            status=200,
            body={"article_id": article.article_id, "iblock_id": article.iblock_id},
        )
        return article


@dataclass
class HttpBitrixCatalogClient:
    """INT-10: paginated element.list plus element.get or a custom article URL."""

    base_url: str
    service_token: str
    list_path: str
    get_path: str
    article_path: str = ""
    timeout_seconds: float = 15.0
    sleep: Callable[[float], None] = time.sleep

    def list_articles(self, iblock_id: int, *, start: int) -> ArticleListPage:
        url = _bitrix_url(
            self.base_url,
            self.list_path,
            {"IBLOCK_ID": iblock_id, "ACTIVE": "Y", "start": start},
        )
        payload = self._get_json(url)
        page = parse_list_payload(payload)
        logger.info(
            "bitrix_full_load list status=200 start=%s count=%s next=%s",
            start,
            len(page.article_ids),
            page.next_start,
        )
        return page

    def get_article(self, iblock_id: int, article_id: int) -> NormalizedArticle:
        if self.article_path:
            path = self.article_path.format(id=article_id)
            url = _bitrix_url(self.base_url, path, {})
        else:
            url = _bitrix_url(
                self.base_url,
                self.get_path,
                {"ID": article_id, "IBLOCK_ID": iblock_id},
            )
        try:
            payload = self._get_json(url)
        except ArticleNotFound:
            raise ArticleNotFound(article_id) from None
        article = normalize_article(
            payload,
            iblock_id=iblock_id,
            article_id=article_id,
        )
        logger.info(
            "bitrix_full_load article status=200 article_id=%s iblock_id=%s",
            article.article_id,
            article.iblock_id,
        )
        return article

    def _get_json(self, url: str) -> Any:
        self._require_config()
        delay = 1.0
        last_error: BitrixClientError | None = None
        for attempt in range(3):
            try:
                return self._get_once(url)
            except (ArticleNotFound, BitrixAuthError):
                raise
            except RetryableBitrixError as exc:
                last_error = exc
                if attempt == 2:
                    raise
                self.sleep(delay)
                delay *= 2
        if last_error is not None:
            raise last_error
        raise BitrixClientError(f"Bitrix request failed: {url}")

    def _require_config(self) -> None:
        if not self.base_url:
            raise BitrixClientError("BITRIX_REST_BASE_URL is not configured")
        if not self.service_token:
            raise BitrixClientError("BITRIX_SERVICE_TOKEN is not configured")

    def _get_once(self, url: str) -> Any:
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {self.service_token}",
                "Accept": "application/json",
                "User-Agent": "sufler-ingest-full-load/1.0",
            },
            method="GET",
        )
        status: int | None = None
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                status = getattr(response, "status", None)
                raw = response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.error(
                "bitrix_full_load status=%s body=%s",
                exc.code,
                body[:300],
            )
            if exc.code == 404:
                raise ArticleNotFound(0) from exc
            if exc.code in {401, 403}:
                raise BitrixAuthError(
                    exc.code,
                    f"Bitrix catalog HTTP {exc.code}: {body[:300]}",
                ) from exc
            if exc.code >= 500:
                raise RetryableBitrixError(
                    f"Bitrix catalog HTTP {exc.code}: {body[:300]}"
                ) from exc
            raise BitrixClientError(
                f"Bitrix catalog HTTP {exc.code}: {body[:300]}"
            ) from exc
        except URLError as exc:
            logger.exception("bitrix_full_load_unreachable")
            raise RetryableBitrixError(f"Bitrix catalog unreachable: {exc}") from exc

        decoded = raw.decode("utf-8", errors="replace")
        try:
            payload = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.error(
                "bitrix_full_load status=%s body=%s",
                status,
                decoded[:300],
            )
            raise BitrixClientError("Bitrix catalog returned invalid JSON") from exc
        return payload


def parse_list_payload(payload: Any) -> ArticleListPage:
    if not isinstance(payload, Mapping):
        raise BitrixClientError("Bitrix element list root must be an object")
    items = payload.get("articles")
    if items is None:
        items = payload.get("result")
    if not isinstance(items, list):
        raise BitrixClientError("Bitrix element list result must be a list")
    article_ids = [_list_item_id(item) for item in items]
    next_raw = payload.get("next")
    next_start: int | None
    if next_raw is None or next_raw == "":
        next_start = None
    else:
        try:
            next_start = int(next_raw)
        except (TypeError, ValueError) as exc:
            raise BitrixClientError(
                "Bitrix element list next must be an integer"
            ) from exc
    return ArticleListPage(article_ids=article_ids, next_start=next_start)


def normalize_article(
    payload: Any,
    *,
    iblock_id: int,
    article_id: int,
) -> NormalizedArticle:
    if not isinstance(payload, Mapping):
        raise BitrixClientError(
            f"Bitrix article {article_id} root must be an object"
        )
    data = _unwrap_article(payload)
    if _is_contract(data):
        return _article_from_contract(
            data,
            iblock_id=iblock_id,
            article_id=article_id,
        )
    return _article_from_raw_element(
        data,
        iblock_id=iblock_id,
        article_id=article_id,
    )


def _unwrap_article(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    result = payload.get("result")
    if isinstance(result, Mapping) and not _is_contract(payload) and "ID" not in payload:
        return result
    return payload


def _is_contract(data: Mapping[str, Any]) -> bool:
    return any(
        key in data for key in ("article_id", "body_plain", "body_html", "visibility_scope")
    )


def _article_from_contract(
    data: Mapping[str, Any],
    *,
    iblock_id: int,
    article_id: int,
) -> NormalizedArticle:
    parsed_id = _optional_positive(data.get("article_id")) or article_id
    parsed_iblock = _optional_positive(data.get("iblock_id")) or iblock_id
    scope: tuple[str, ...] | None
    if "visibility_scope" in data:
        raw_scope = data.get("visibility_scope")
        if not isinstance(raw_scope, list):
            scope = ()
        else:
            scope = tuple(
                item.strip()
                for item in raw_scope
                if isinstance(item, str) and item.strip()
            )
    else:
        scope = None
    version_number = _optional_positive(data.get("version_number"))
    section_id = _optional_positive(data.get("section_id"))
    return NormalizedArticle(
        article_id=parsed_id,
        iblock_id=parsed_iblock,
        version_id=data.get("version_id"),
        version_number=version_number,
        title=_as_text(data.get("title")),
        preview=_as_text(data.get("preview")),
        body_html=_as_text(data.get("body_html")),
        body_plain=_as_text(data.get("body_plain")),
        permalink=_as_text(data.get("permalink")),
        locale=_as_text(data.get("locale")) or "ru",
        visibility_scope=scope,
        status=_as_text(data.get("status")) or None,
        section_id=section_id,
        updated_at=_as_text(data.get("updated_at")) or None,
        apply_default_scope=False,
    )


def _article_from_raw_element(
    data: Mapping[str, Any],
    *,
    iblock_id: int,
    article_id: int,
) -> NormalizedArticle:
    parsed_id = _optional_positive(data.get("ID")) or article_id
    parsed_iblock = _optional_positive(data.get("IBLOCK_ID")) or iblock_id
    plain, html = _bitrix_text(data.get("DETAIL_TEXT"))
    preview, _preview_html = _bitrix_text(data.get("PREVIEW_TEXT"))
    active = data.get("ACTIVE")
    if active is None:
        status = "published"
    elif str(active).strip().upper() in {"Y", "YES", "1", "TRUE"}:
        status = "published"
    else:
        status = "archived"
    scope_raw = data.get("visibility_scope")
    if isinstance(scope_raw, list):
        scope = tuple(
            item.strip()
            for item in scope_raw
            if isinstance(item, str) and item.strip()
        )
        apply_default = False
    else:
        scope = None
        apply_default = True
    return NormalizedArticle(
        article_id=parsed_id,
        iblock_id=parsed_iblock,
        version_id=data.get("version_id"),
        version_number=_optional_positive(data.get("version_number")),
        title=_as_text(data.get("NAME")),
        preview=preview,
        body_html=html,
        body_plain=plain,
        permalink=_as_text(data.get("permalink"))
        or _as_text(data.get("DETAIL_PAGE_URL")),
        locale=_as_text(data.get("locale")) or "ru",
        visibility_scope=scope,
        status=status,
        section_id=_optional_positive(data.get("IBLOCK_SECTION_ID"))
        or _optional_positive(data.get("section_id")),
        updated_at=_as_text(data.get("TIMESTAMP_X"))
        or _as_text(data.get("updated_at"))
        or None,
        apply_default_scope=apply_default,
    )


def _list_item_id(item: Any) -> int:
    if isinstance(item, Mapping):
        for key in ("article_id", "ID", "id"):
            parsed = _optional_positive(item.get(key))
            if parsed is not None:
                return parsed
        raise BitrixClientError("Bitrix list item has no article id")
    parsed = _optional_positive(item)
    if parsed is None:
        raise BitrixClientError("Bitrix list item has no article id")
    return parsed


def _optional_positive(value: Any) -> int | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _bitrix_text(value: Any) -> tuple[str, str]:
    """Return (plain, html) for a Bitrix text field or `{TEXT, TYPE}` object."""
    if isinstance(value, str):
        return value, ""
    if isinstance(value, Mapping):
        text = value.get("TEXT")
        text = text.strip() if isinstance(text, str) else ""
        kind = value.get("TYPE")
        if isinstance(kind, str) and kind.strip().upper() == "HTML":
            return "", text
        return text, ""
    return "", ""


def _bitrix_url(base_url: str, path: str, query: Mapping[str, Any]) -> str:
    relative = path.lstrip("/")
    filtered = {key: value for key, value in query.items() if value is not None}
    if filtered:
        relative = f"{relative}?{urlencode(filtered)}"
    return urljoin(base_url.rstrip("/") + "/", relative)


_MOCK_CATALOG = MockBitrixCatalogClient()


def reset_mock_bitrix_catalog_client() -> MockBitrixCatalogClient:
    global _MOCK_CATALOG
    _MOCK_CATALOG = MockBitrixCatalogClient()
    return _MOCK_CATALOG


def get_mock_bitrix_catalog_client() -> MockBitrixCatalogClient:
    return _MOCK_CATALOG


def get_bitrix_catalog_client() -> BitrixCatalogClient:
    if ingest_mode() == "mock" or not getattr(settings, "BITRIX_REST_BASE_URL", ""):
        return _MOCK_CATALOG
    return HttpBitrixCatalogClient(
        base_url=str(settings.BITRIX_REST_BASE_URL),
        service_token=str(getattr(settings, "BITRIX_SERVICE_TOKEN", "") or ""),
        list_path=str(
            getattr(
                settings,
                "BITRIX_ELEMENT_LIST_PATH",
                "/rest/iblock.element.list",
            )
        ),
        get_path=str(
            getattr(
                settings,
                "BITRIX_ELEMENT_GET_PATH",
                "/rest/iblock.element.get",
            )
        ),
        article_path=str(getattr(settings, "BITRIX_ARTICLE_PATH", "") or ""),
        timeout_seconds=float(
            getattr(settings, "BITRIX_HTTP_TIMEOUT_SECONDS", 15.0)
        ),
    )
