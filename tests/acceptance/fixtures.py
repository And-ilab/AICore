"""Shared arrange helpers for P0-04 acceptance modules.

Requires ``django.setup()`` before import (done by each test module / conftest).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client

from auth.roles import ROLES_BY_CODE
from ingest.models import CCProductionChunk
from ingest.pipeline import deterministic_embedding


def user_for_role(role_code: str, *, prefix: str = "acc") -> Any:
    role = ROLES_BY_CODE[role_code]
    user = get_user_model().objects.create_user(
        username=f"{prefix}-{role_code}-{uuid.uuid4().hex[:8]}",
        password="acceptance-test-password",
    )
    group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
    user.groups.add(group)
    return user


def api_client_for(role_code: str, *, prefix: str = "acc") -> Client:
    client = Client()
    client.force_login(user_for_role(role_code, prefix=prefix))
    return client


def seed_cc_chunk(
    *,
    article_id: int,
    title: str,
    content: str,
    permalink: str | None = None,
) -> CCProductionChunk:
    return CCProductionChunk.objects.create(
        article_id=article_id,
        version_id=1,
        chunk_index=0,
        title=title,
        content=content,
        permalink=permalink or f"https://suz.local/articles/{article_id}",
        locale="ru",
        visibility_scope=["kc_operator"],
        checksum=f"sha256:{article_id:064x}",
        embedding_model="deterministic-dev",
        embedding=deterministic_embedding(content),
    )


def post_json(client: Client, url: str, payload: dict[str, Any], **extra):
    return client.post(
        url,
        data=json.dumps(payload, ensure_ascii=False),
        content_type="application/json",
        **extra,
    )


def parse_sse_content(raw: bytes | str) -> tuple[str, bool]:
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    content = ""
    done = False
    for block in text.split("\n\n"):
        block = block.strip("\n")
        if not block or block.startswith(":"):
            continue
        if not block.startswith("data:"):
            continue
        payload = block[len("data:") :].strip()
        if payload == "[DONE]":
            done = True
            continue
        chunk = json.loads(payload)
        delta = chunk["choices"][0]["delta"]
        content += delta.get("content") or ""
    return content, done
