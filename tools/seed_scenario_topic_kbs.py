#!/usr/bin/env python3
"""Upload each scenario-topic .txt into its own contact-center KB."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from seed_manual_kb import ApiClient, guess_content_type, multipart  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DOCS = [
    (
        REPO / "local/kb/scenario-topics/avtokredit-belarusbank.txt",
        "Автокредит Беларусбанка",
    ),
    (
        REPO / "local/kb/scenario-topics/karta-nesovershennoletnego-belarusbank.txt",
        "Карта несовершеннолетнему Беларусбанка",
    ),
    (
        REPO / "local/kb/scenario-topics/oplata-telefonom-nfc-belarusbank.txt",
        "Оплата телефоном / NFC Беларусбанка",
    ),
    (
        REPO / "local/kb/scenario-topics/perevod-v-rf-belarusbank.txt",
        "Перевод в РФ Беларусбанка",
    ),
]


def login(base_url: str) -> ApiClient:
    password = os.environ.get("AUTH_MOCK_LDAP_DEFAULT_PASSWORD") or "dev-only-password"
    errors: list[str] = []
    for candidate in dict.fromkeys(
        [password, "dev-only-password", "replace-with-dev-only-password"]
    ):
        try:
            client = ApiClient(base_url)
            client.login("dev-role-02", candidate)
            return client
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
    raise RuntimeError("login failed: " + " | ".join(errors))


def print_status(client: ApiClient) -> None:
    wanted = {name for _, name in DOCS}
    status, listed = client.request("GET", "/api/admin/kb/")
    items = (listed or {}).get("items") if isinstance(listed, dict) else []
    for kb in items or []:
        if kb.get("name") not in wanted:
            continue
        _, detail = client.request("GET", f"/api/admin/kb/{kb['id']}/")
        docs = (detail or {}).get("documents") or []
        print(
            json.dumps(
                {
                    "id": kb.get("id"),
                    "name": kb.get("name"),
                    "status": (detail or {}).get("status"),
                    "document_count": (detail or {}).get("document_count"),
                    "chunk_count": (detail or {}).get("chunk_count"),
                    "documents": [
                        {
                            "id": d.get("id"),
                            "filename": d.get("filename"),
                            "status": d.get("status"),
                            "chunk_count": d.get("chunk_count"),
                        }
                        for d in docs
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )


def main() -> int:
    args = [a for a in sys.argv[1:] if a]
    check_only = "--check" in args
    args = [a for a in args if a != "--check"]
    base_url = args[0] if args else "http://127.0.0.1:8001"
    print(f"Base URL: {base_url}", flush=True)
    client = login(base_url)
    if check_only:
        print_status(client)
        return 0

    status, listed = client.request("GET", "/api/admin/kb/")
    if status >= 400 or not isinstance(listed, dict):
        print(f"ERROR list KB: {status} {listed}", file=sys.stderr)
        return 3
    items = listed.get("items") or []

    failed = 0
    for path, kb_name in DOCS:
        print(f"\n=== {kb_name} / {path.name} ===", flush=True)
        if not path.is_file():
            print(f"MISSING {path}", file=sys.stderr)
            failed += 1
            continue
        kb = next((item for item in items if item.get("name") == kb_name), None)
        if kb is None:
            status, kb = client.request(
                "POST",
                "/api/admin/kb/",
                data=json.dumps(
                    {
                        "name": kb_name,
                        "scope": "contact_center",
                        "description": (
                            "Публичные статьи belarusbank.by по теме. "
                            f"Один документ: {path.name}"
                        ),
                    }
                ).encode("utf-8"),
                content_type="application/json",
            )
            if status >= 400 or not isinstance(kb, dict):
                print(f"FAIL create KB: {status} {kb}", file=sys.stderr)
                failed += 1
                continue
            items.append(kb)
            print(f"Created KB id={kb.get('id')}", flush=True)
        else:
            print(f"Using existing KB id={kb.get('id')}", flush=True)

        kb_id = kb["id"]
        status, detail = client.request("GET", f"/api/admin/kb/{kb_id}/")
        existing = {
            doc.get("filename")
            for doc in (detail.get("documents") if isinstance(detail, dict) else []) or []
        }
        if path.name in existing:
            print(f"SKIP exists: {path.name}", flush=True)
            continue

        body, content_type = multipart(
            {},
            [("file", path.name, path.read_bytes(), guess_content_type(path))],
        )
        print(f"Uploading {path.stat().st_size} bytes…", flush=True)
        status, result = client.request(
            "POST",
            f"/api/admin/kb/{kb_id}/upload/",
            data=body,
            content_type=content_type,
        )
        if status >= 400:
            print(f"FAIL upload: {status} {result}", file=sys.stderr)
            failed += 1
            continue
        doc = result.get("document") if isinstance(result, dict) else None
        print(
            f"OK doc_id={doc and doc.get('id')} "
            f"status={doc and doc.get('status')} "
            f"chunks={doc and doc.get('chunk_count')}",
            flush=True,
        )

    print("\nDone", flush=True)
    return 0 if failed == 0 else 5


if __name__ == "__main__":
    raise SystemExit(main())
