#!/usr/bin/env python3
"""Upload local/kb/manual documents into Hub KB via Admin API.

Usage:
  py -3 tools/seed_manual_kb.py
  py -3 tools/seed_manual_kb.py --base-url http://127.0.0.1:8001
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DIR = REPO / "local" / "kb" / "manual"
ALLOWED = {".pdf", ".doc", ".docx", ".txt", ".rtf", ".xlsx", ".pptx", ".png", ".jpg", ".jpeg"}
KB_NAME = "Тестовые статьи (manual)"
KB_SLUG_HINT = "testovye-stati-manual"


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/")
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
        )

    def _csrf(self) -> str:
        for cookie in self.jar:
            if cookie.name == "csrftoken":
                return cookie.value
        return ""

    def request(
        self,
        method: str,
        path: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        content_type: str | None = None,
    ) -> tuple[int, object]:
        req_headers = {"Accept": "application/json", **(headers or {})}
        if content_type:
            req_headers["Content-Type"] = content_type
        if method in {"POST", "PUT", "PATCH", "DELETE"}:
            token = self._csrf()
            if token:
                req_headers["X-CSRFToken"] = token
                req_headers.setdefault("Referer", self.base + "/")
        request = urllib.request.Request(
            self.base + path,
            data=data,
            headers=req_headers,
            method=method,
        )
        try:
            with self.opener.open(request, timeout=120) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        if not raw:
            return status, None
        try:
            return status, json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return status, raw.decode("utf-8", errors="replace")

    def login(self, username: str, password: str) -> None:
        # Ensure CSRF cookie
        self.request("GET", "/api/auth/me/")
        status, body = self.request(
            "POST",
            "/api/auth/login/",
            data=json.dumps({"username": username, "password": password}).encode("utf-8"),
            content_type="application/json",
        )
        if status >= 400:
            raise RuntimeError(f"login failed: {status} {body}")
        status, me = self.request("GET", "/api/auth/me/")
        if status >= 400 or not isinstance(me, dict) or not me.get("authenticated"):
            raise RuntimeError(f"session not authenticated: {status} {me}")
        print(f"Logged in as {me.get('username')} roles={me.get('roles')}")


def multipart(fields: dict[str, str], files: list[tuple[str, str, bytes, str]]) -> tuple[bytes, str]:
    boundary = "----SuflerSeedBoundary7MA4YWxkTrZu0gW"
    lines: list[bytes] = []
    for name, value in fields.items():
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        lines.append(b"")
        lines.append(value.encode("utf-8"))
    for field, filename, content, content_type in files:
        lines.append(f"--{boundary}".encode())
        lines.append(
            (
                f'Content-Disposition: form-data; name="{field}"; '
                f'filename="{filename}"'
            ).encode("utf-8")
        )
        lines.append(f"Content-Type: {content_type}".encode())
        lines.append(b"")
        lines.append(content)
    lines.append(f"--{boundary}--".encode())
    lines.append(b"")
    body = b"\r\n".join(lines)
    return body, f"multipart/form-data; boundary={boundary}"


def guess_content_type(path: Path) -> str:
    return {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
        ".rtf": "application/rtf",
    }.get(path.suffix.lower(), "application/octet-stream")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Backend base URL (host port mapped from compose)",
    )
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--user", default="dev-role-02")
    parser.add_argument(
        "--password",
        default="",
        help="Mock LDAP password (default: AUTH_MOCK_LDAP_DEFAULT_PASSWORD or dev-only-password)",
    )
    parser.add_argument("--kb-name", default=KB_NAME)
    args = parser.parse_args()

    docs = sorted(
        p
        for p in args.dir.iterdir()
        if p.is_file() and p.suffix.lower() in ALLOWED
    )
    if not docs:
        print(f"No uploadable documents in {args.dir}", file=sys.stderr)
        return 1

    password = args.password.strip()
    if not password:
        password = (
            __import__("os").environ.get("AUTH_MOCK_LDAP_DEFAULT_PASSWORD")
            or "dev-only-password"
        )

    client = ApiClient(args.base_url)
    login_errors: list[str] = []
    for candidate in dict.fromkeys(
        [
            password,
            "dev-only-password",
            "replace-with-dev-only-password",
        ]
    ):
        try:
            client = ApiClient(args.base_url)
            client.login(args.user, candidate)
            break
        except Exception as exc:
            login_errors.append(f"{candidate}: {exc}")
    else:
        print("ERROR: login failed for all password candidates", file=sys.stderr)
        for line in login_errors:
            print(f"  - {line}", file=sys.stderr)
        print(
            "Is backend up? Try: cd infra && docker compose up -d backend",
            file=sys.stderr,
        )
        return 2

    status, listed = client.request("GET", "/api/admin/kb/")
    if status >= 400 or not isinstance(listed, dict):
        print(f"ERROR list KB: {status} {listed}", file=sys.stderr)
        return 3
    items = listed.get("items") or []
    kb = next((item for item in items if item.get("name") == args.kb_name), None)
    if kb is None:
        status, kb = client.request(
            "POST",
            "/api/admin/kb/",
            data=json.dumps(
                {
                    "name": args.kb_name,
                    "scope": "contact_center",
                    "description": (
                        "Локальные тестовые документы из local/kb/manual "
                        "для задачи UI Admin center / Базы знаний КЦ."
                    ),
                }
            ).encode("utf-8"),
            content_type="application/json",
        )
        if status >= 400 or not isinstance(kb, dict):
            print(f"ERROR create KB: {status} {kb}", file=sys.stderr)
            return 4
        print(f"Created KB id={kb.get('id')} slug={kb.get('slug')}")
    else:
        print(f"Using existing KB id={kb.get('id')} slug={kb.get('slug')}")

    kb_id = kb["id"]
    status, detail = client.request("GET", f"/api/admin/kb/{kb_id}/")
    existing_names = {
        doc.get("filename")
        for doc in (detail.get("documents") if isinstance(detail, dict) else []) or []
    }

    uploaded = 0
    skipped = 0
    failed = 0
    for path in docs:
        if path.name in existing_names:
            print(f"SKIP exists: {path.name}")
            skipped += 1
            continue
        body, content_type = multipart(
            {},
            [("file", path.name, path.read_bytes(), guess_content_type(path))],
        )
        status, result = client.request(
            "POST",
            f"/api/admin/kb/{kb_id}/upload/",
            data=body,
            content_type=content_type,
        )
        if status >= 400:
            print(f"FAIL {path.name}: {status} {result}")
            failed += 1
            continue
        doc = result.get("document") if isinstance(result, dict) else None
        print(
            f"OK  {path.name}: doc_id={doc and doc.get('id')} "
            f"status={doc and doc.get('status')} chunks={doc and doc.get('chunk_count')}"
        )
        uploaded += 1

    status, final = client.request("GET", f"/api/admin/kb/{kb_id}/")
    print("---")
    print(
        json.dumps(
            {
                "kb_id": kb_id,
                "kb_name": args.kb_name,
                "uploaded": uploaded,
                "skipped": skipped,
                "failed": failed,
                "document_count": final.get("document_count") if isinstance(final, dict) else None,
                "chunk_count": final.get("chunk_count") if isinstance(final, dict) else None,
                "status": final.get("status") if isinstance(final, dict) else None,
                "documents": [
                    {
                        "id": d.get("id"),
                        "filename": d.get("filename"),
                        "status": d.get("status"),
                        "chunk_count": d.get("chunk_count"),
                    }
                    for d in (
                        (final.get("documents") if isinstance(final, dict) else None) or []
                    )
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if failed == 0 else 5


if __name__ == "__main__":
    raise SystemExit(main())
