"""Convert curated OpenAPI → Postman Collection v2.1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from api_docs.openapi_v1 import build_openapi_v1

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "docs" / "api" / "postman_collection.json"


def _path_segments(path: str) -> list[str]:
    """OpenAPI `{id}` → Postman `:id` path segments."""
    segments: list[str] = []
    for segment in path.strip("/").split("/"):
        if not segment:
            continue
        if segment.startswith("{") and segment.endswith("}"):
            segments.append(f":{segment[1:-1]}")
        else:
            segments.append(segment)
    return segments


def _query_from_parameters(
    parameters: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    query: list[dict[str, Any]] = []
    for param in parameters or []:
        if param.get("in") != "query":
            continue
        schema = param.get("schema") or {}
        default = schema.get("default", "")
        query.append(
            {
                "key": param["name"],
                "value": "" if default is None else str(default),
                "description": param.get("description") or "",
                "disabled": not param.get("required", False),
            }
        )
    return query


def _headers_from_operation(operation: dict[str, Any]) -> list[dict[str, str]]:
    headers: list[dict[str, str]] = [
        {"key": "Accept", "value": "application/json"},
    ]
    if "requestBody" in operation:
        content = (operation.get("requestBody") or {}).get("content") or {}
        if "multipart/form-data" not in content:
            headers.append({"key": "Content-Type", "value": "application/json"})
    for param in operation.get("parameters") or []:
        if param.get("in") == "header":
            headers.append(
                {
                    "key": param["name"],
                    "value": "",
                    "description": param.get("description") or "",
                }
            )
    for requirement in operation.get("security") or []:
        if "SuzHmac" in requirement:
            headers.append(
                {
                    "key": "X-Sufler-Signature",
                    "value": "{{suz_hmac_signature}}",
                    "description": "HMAC-SHA256(raw body, shared secret)",
                }
            )
        if "BearerAuth" in requirement:
            headers.append(
                {
                    "key": "Authorization",
                    "value": "Bearer {{access_token}}",
                    "description": "Optional bearer",
                }
            )
    return headers


def _body_from_operation(operation: dict[str, Any]) -> dict[str, Any] | None:
    body = operation.get("requestBody")
    if not body:
        return None
    content = body.get("content") or {}
    multipart = content.get("multipart/form-data")
    if multipart:
        schema = multipart.get("schema") or {}
        formdata: list[dict[str, Any]] = []
        for key, spec in (schema.get("properties") or {}).items():
            is_file = spec.get("format") == "binary"
            item: dict[str, Any] = {
                "key": key,
                "type": "file" if is_file else "text",
                "description": spec.get("description") or "",
            }
            if is_file:
                item["src"] = ""
            else:
                item["value"] = str(spec.get("example") or "")
            formdata.append(item)
        return {"mode": "formdata", "formdata": formdata}
    json_content = content.get("application/json") or {}
    example = json_content.get("example")
    if example is None:
        examples = json_content.get("examples") or {}
        if examples:
            first = next(iter(examples.values()))
            example = first.get("value")
    if example is None:
        example = {}
    return {
        "mode": "raw",
        "raw": json.dumps(example, ensure_ascii=False, indent=2),
        "options": {"raw": {"language": "json"}},
    }


def openapi_to_postman(document: dict[str, Any] | None = None) -> dict[str, Any]:
    doc = document or build_openapi_v1()
    server = (doc.get("servers") or [{"url": "http://127.0.0.1:8000"}])[0]["url"]
    if "://" not in server:
        server = f"http://127.0.0.1:8000{server}"
    parsed = urlparse(server)
    host = parsed.hostname or "127.0.0.1"
    port = str(parsed.port or (443 if parsed.scheme == "https" else 8000))

    folders: dict[str, list[dict[str, Any]]] = {}
    for path, methods in sorted((doc.get("paths") or {}).items()):
        for method, operation in methods.items():
            if method.startswith("x-") or not isinstance(operation, dict):
                continue
            tag = (operation.get("tags") or ["default"])[0]
            folders.setdefault(tag, [])
            request: dict[str, Any] = {
                "method": method.upper(),
                "header": _headers_from_operation(operation),
                "url": {
                    "raw": f"{{{{base_url}}}}{path}",
                    "protocol": parsed.scheme or "http",
                    "host": ["{{base_host}}"],
                    "port": "{{base_port}}",
                    "path": _path_segments(path),
                    "query": _query_from_parameters(operation.get("parameters")),
                },
                "description": operation.get("description") or "",
            }
            body = _body_from_operation(operation)
            if body:
                request["body"] = body
            folders[tag].append(
                {
                    "name": operation.get("summary")
                    or operation.get("operationId")
                    or f"{method.upper()} {path}",
                    "request": request,
                }
            )

    return {
        "info": {
            "name": doc.get("info", {}).get("title", "Sufler AI Hub API"),
            "description": doc.get("info", {}).get("description", ""),
            "schema": (
                "https://schema.getpostman.com/json/collection/v2.1.0/"
                "collection.json"
            ),
            "_postman_id": "sufler-ai-hub-v1",
        },
        "variable": [
            {"key": "base_url", "value": f"{parsed.scheme}://{host}:{port}"},
            {"key": "base_host", "value": host},
            {"key": "base_port", "value": port},
            {"key": "access_token", "value": ""},
            {"key": "suz_hmac_signature", "value": ""},
        ],
        "item": [
            {"name": tag, "item": items} for tag, items in folders.items()
        ],
    }


def export_postman_collection(output: Path = DEFAULT_OUTPUT) -> Path:
    collection = openapi_to_postman()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(collection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Postman collection from curated OpenAPI v1",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to postman_collection.json",
    )
    args = parser.parse_args()
    path = export_postman_collection(args.output)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
