from __future__ import annotations

import json
from typing import Any, Mapping

from django.core.exceptions import ValidationError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from audit import emit_kb_change
from auth.decorators import (
    permission_denied_response,
    require_permissions,
    roles_required,
)
from auth.roles import (
    PERM_ASSISTANT_ADMIN,
    PERM_KB_ADMIN,
    PERM_PROMPTS_ADMIN,
    PERM_QU_ADMIN,
    role_codes_for_user,
)
from assistant.doc_templates import (
    create_template,
    delete_template,
    get_template,
    list_templates,
    serialize_template,
    update_template,
)
from assistant.rpa import (
    RpaError,
    create_scenario as create_rpa_scenario,
    delete_scenario as delete_rpa_scenario,
    list_scenarios as list_rpa_scenarios,
    update_scenario as update_rpa_scenario,
)
from assistant.sql_access import (
    SqlAccessError,
    create_access,
    delete_access,
    list_accesses,
    update_access,
)
from hub.assistant_admin import (
    AssistantAdminError,
    create_assistant_kb,
    create_prompt,
    delete_assistant_document,
    delete_assistant_kb,
    delete_prompt,
    get_assistant_kb,
    get_prompt,
    list_assistant_kbs,
    list_capabilities,
    list_prompts,
    reindex_assistant_kb,
    update_capability,
    update_prompt,
    upload_assistant_document,
)
from hub.website_crawl import get_latest_crawl, start_website_crawl
from hub.kb_admin import (
    KnowledgeBaseError,
    create_knowledge_base,
    delete_document,
    delete_knowledge_base,
    get_knowledge_base,
    list_knowledge_bases,
    reindex_knowledge_base,
    upload_document,
)
from hub.model_catalog import apply_profile_selection, choices_for_ocr
from hub.model_registry_store import (
    get_model_settings,
    serialize_model_settings,
    update_model_settings,
)
from hub.models import AssistantKnowledgeBase, ContactCenterKnowledgeBase
from hub.sufler_policy import (
    get_sufler_policy,
    serialize_sufler_policy,
    update_sufler_policy,
)
from hub.scenario_service import (
    ScenarioAdminError,
    create_scenario,
    get_scenario,
    list_scenarios,
    serialize_scenario,
    update_scenario,
)
from hub.skill_store import (
    SkillNotFound,
    SkillStoreError,
    create_org_skill,
    delete_org_skill,
    get_org_skill,
    list_org_skills,
    serialize_skill,
    update_org_skill,
)
from orchestrator.scenario_engine import run_test_dialog
from qu.admin_service import (
    QuAdminError,
    create_example,
    delete_example,
    list_bindable_documents,
    list_examples,
    review_example,
    serialize_example,
    serialize_policy,
    update_example,
    update_policy,
)
from qu.models import QuReferenceExample
from qu.assistant_retrieval import preview_admin_query


ADMIN_ROLES = (
    "software_administrator",
    "llm_knowledge_base_administrator",
    "contact_center_module_administrator",
    "ai_assistant_module_administrator",
    "document_recognition_module_administrator",
)
PROFILE_ROLES = {
    "assistant_bank": {
        "software_administrator",
        "llm_knowledge_base_administrator",
        "ai_assistant_module_administrator",
    },
    "sufler_cc": {
        "software_administrator",
        "contact_center_module_administrator",
    },
}


def _profile(request: HttpRequest) -> str:
    profile = request.GET.get("profile", "")
    if profile not in PROFILE_ROLES:
        raise ValueError("profile must be assistant_bank or sufler_cc")
    return profile


def _check_profile_access(
    request: HttpRequest,
    profile: str,
) -> JsonResponse | None:
    if role_codes_for_user(request.user).intersection(PROFILE_ROLES[profile]):
        return None
    return permission_denied_response(
        request,
        required=(f"model_registry:{profile}",),
        force_json=True,
    )


def _parse_update_payload(
    request: HttpRequest,
) -> tuple[dict[str, Any], dict[str, str]]:
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Request body must be valid JSON") from exc
    if not isinstance(body, Mapping):
        raise ValueError("Request body must be a JSON object")
    generation = body.get("generation", {})
    rag = body.get("rag", {})
    if not isinstance(generation, Mapping) or not isinstance(rag, Mapping):
        raise ValueError("generation and rag must be JSON objects")
    allowed_root = {"generation", "rag", "selection"}
    unknown_root = set(body) - allowed_root
    if unknown_root:
        raise ValueError(
            f"Unknown sections: {', '.join(sorted(unknown_root))}"
        )
    generation_fields = {
        "temperature",
        "top_p",
        "max_tokens",
        "response_chars_max",
        "preset",
    }
    rag_fields = {
        "chunk_size_tokens",
        "chunk_overlap_tokens",
        "context_inclusion",
        "deterministic_answer",
    }
    for section_name, section, fields in (
        ("generation", generation, generation_fields),
        ("rag", rag, rag_fields),
    ):
        missing = fields - set(section)
        unknown = set(section) - fields
        # preset is optional for backward-compatible clients
        if section_name == "generation":
            missing -= {"preset"}
        if missing:
            raise ValueError(
                f"{section_name} is missing: {', '.join(sorted(missing))}"
            )
        if unknown:
            raise ValueError(
                f"{section_name} has unknown fields: "
                f"{', '.join(sorted(unknown))}"
            )
    flat = {
        "temperature": generation.get("temperature"),
        "top_p": generation.get("top_p"),
        "max_tokens": generation.get("max_tokens"),
        "response_chars_max": generation.get("response_chars_max"),
        "chunk_size_tokens": rag.get("chunk_size_tokens"),
        "chunk_overlap_tokens": rag.get("chunk_overlap_tokens"),
        "context_inclusion_threshold": rag.get("context_inclusion"),
        "deterministic_answer_threshold": rag.get(
            "deterministic_answer"
        ),
    }
    if "preset" in generation:
        flat["preset"] = generation.get("preset")
    selection = body.get("selection") or {}
    parsed_selection: dict[str, str] = {}
    if selection:
        if not isinstance(selection, Mapping):
            raise ValueError("selection must be a JSON object")
        unknown_selection = set(selection) - {"llm", "speech", "answer"}
        if unknown_selection:
            raise ValueError(
                "selection has unknown fields: "
                f"{', '.join(sorted(unknown_selection))}"
            )
        for key in ("llm", "speech", "answer"):
            if key not in selection or selection[key] in (None, ""):
                continue
            value = selection[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"selection.{key} must be a non-empty string")
            parsed_selection[key] = value.strip()
    return flat, parsed_selection


@require_http_methods(["GET", "PUT"])
@roles_required(*ADMIN_ROLES, api=True)
def model_params(request: HttpRequest) -> JsonResponse:
    try:
        profile = _profile(request)
    except ValueError as exc:
        return JsonResponse(
            {"error": "validation_error", "details": {"profile": [str(exc)]}},
            status=400,
        )
    denied = _check_profile_access(request, profile)
    if denied is not None:
        return denied

    try:
        if request.method == "PUT":
            payload, selection = _parse_update_payload(request)
            instance = update_model_settings(
                profile,
                payload,
                username=request.user.get_username(),
            )
            if selection:
                apply_profile_selection(
                    profile,
                    selection,
                    username=request.user.get_username(),
                )
            emit_kb_change(
                request=request,
                profile=profile,
                revision=instance.revision,
                changed_fields=payload.keys(),
            )
        else:
            instance = get_model_settings(profile)
    except ValidationError as exc:
        details = getattr(exc, "message_dict", {"form": exc.messages})
        return JsonResponse(
            {"error": "validation_error", "details": details},
            status=400,
        )
    except (TypeError, ValueError) as exc:
        return JsonResponse(
            {"error": "validation_error", "details": {"form": [str(exc)]}},
            status=400,
        )

    return JsonResponse(serialize_model_settings(instance))


@require_http_methods(["GET", "PUT"])
@roles_required(*ADMIN_ROLES, api=True)
def ocr_model_choice(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "PUT":
            try:
                body = json.loads(request.body or b"{}")
            except json.JSONDecodeError as exc:
                raise ValueError("Request body must be valid JSON") from exc
            if not isinstance(body, Mapping):
                raise ValueError("Request body must be a JSON object")
            model_id = body.get("model_id")
            if not isinstance(model_id, str) or not model_id.strip():
                raise ValueError("model_id is required")
            from hub.model_catalog import SLOT_OCR, save_model

            save_model(
                SLOT_OCR,
                model_id,
                username=request.user.get_username(),
            )
    except (TypeError, ValueError) as exc:
        return JsonResponse(
            {"error": "validation_error", "details": {"model_id": [str(exc)]}},
            status=400,
        )
    return JsonResponse(choices_for_ocr())


SUFLER_POLICY_ROLES = (
    "software_administrator",
    "llm_knowledge_base_administrator",
    "contact_center_module_administrator",
)


def _parse_sufler_policy_payload(request: HttpRequest) -> dict[str, Any]:
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Request body must be valid JSON") from exc
    if not isinstance(body, Mapping):
        raise ValueError("Request body must be a JSON object")
    allowed = {
        "telephony_min_relevance_percent",
        "clarify_min_relevance_percent",
        "max_hints",
        "default_mode",
    }
    unknown = set(body) - allowed
    if unknown:
        raise ValueError(f"Unknown fields: {', '.join(sorted(unknown))}")
    payload: dict[str, Any] = {}
    for field in (
        "telephony_min_relevance_percent",
        "clarify_min_relevance_percent",
        "max_hints",
    ):
        if field not in body:
            continue
        try:
            payload[field] = int(body[field])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} must be an integer") from exc
    if "default_mode" in body:
        mode = str(body.get("default_mode") or "").strip()
        if not mode:
            raise ValueError("default_mode must be a non-empty string")
        payload["default_mode"] = mode
    if not payload:
        raise ValueError("No policy fields to update")
    return payload


@require_http_methods(["GET", "PUT"])
@roles_required(*SUFLER_POLICY_ROLES, api=True)
def sufler_policies(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "PUT":
            payload = _parse_sufler_policy_payload(request)
            instance = update_sufler_policy(
                payload,
                username=request.user.get_username(),
            )
        else:
            instance = get_sufler_policy()
    except ValidationError as exc:
        details = getattr(exc, "message_dict", {"form": exc.messages})
        return JsonResponse(
            {"error": "validation_error", "details": details},
            status=400,
        )
    except (TypeError, ValueError) as exc:
        return JsonResponse(
            {"error": "validation_error", "details": {"form": [str(exc)]}},
            status=400,
        )
    return JsonResponse(serialize_sufler_policy(instance))


@require_http_methods(["POST"])
@require_permissions(PERM_QU_ADMIN, api=True)
def qu_preview(request: HttpRequest) -> JsonResponse:
    try:
        body = json.loads(request.body or b"{}")
        if not isinstance(body, Mapping):
            raise ValueError("Request body must be a JSON object")
        query = body.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        limit = body.get("limit", 5)
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("limit must be an integer")
        result = preview_admin_query(query, limit=limit)
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"body": ["Request body must be valid JSON"]},
            },
            status=400,
        )
    except ValueError as exc:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"query": [str(exc)]},
            },
            status=400,
        )
    return JsonResponse(result)


def _qu_admin_error(exc: Exception) -> JsonResponse:
    return JsonResponse(
        {
            "error": "validation_error",
            "details": {"request": [str(exc)]},
        },
        status=400,
    )


@require_http_methods(["GET", "POST"])
@require_permissions(PERM_QU_ADMIN, api=True)
def qu_examples(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        status = str(request.GET.get("status") or "").strip()
        return JsonResponse(list_examples(status=status))
    try:
        body = _parse_json_object(request)
        created = create_example(body, username=request.user.get_username())
    except (AssistantAdminError, QuAdminError) as exc:
        return _qu_admin_error(exc)
    return JsonResponse(created, status=201)


@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@require_permissions(PERM_QU_ADMIN, api=True)
def qu_example_detail(request: HttpRequest, example_id: int) -> JsonResponse:
    try:
        if request.method == "GET":
            item = QuReferenceExample.objects.get(pk=example_id)
            return JsonResponse(serialize_example(item))
        if request.method == "DELETE":
            delete_example(example_id)
            return JsonResponse({"ok": True})
        body = _parse_json_object(request)
        updated = update_example(example_id, body)
    except QuReferenceExample.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)
    except (AssistantAdminError, QuAdminError) as exc:
        if str(exc) == "example not found":
            return JsonResponse({"error": "not_found"}, status=404)
        return _qu_admin_error(exc)
    return JsonResponse(updated)


@require_http_methods(["POST"])
@require_permissions(PERM_QU_ADMIN, api=True)
def qu_example_review(request: HttpRequest, example_id: int) -> JsonResponse:
    try:
        body = _parse_json_object(request)
        updated = review_example(
            example_id,
            body,
            username=request.user.get_username(),
        )
    except (AssistantAdminError, QuAdminError) as exc:
        if str(exc) == "example not found":
            return JsonResponse({"error": "not_found"}, status=404)
        return _qu_admin_error(exc)
    return JsonResponse(updated)


@require_http_methods(["GET", "PUT", "PATCH"])
@require_permissions(PERM_QU_ADMIN, api=True)
def qu_policy(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse(serialize_policy())
    try:
        body = _parse_json_object(request)
        updated = update_policy(body, username=request.user.get_username())
    except (AssistantAdminError, QuAdminError) as exc:
        return _qu_admin_error(exc)
    return JsonResponse(updated)


@require_http_methods(["GET"])
@require_permissions(PERM_QU_ADMIN, api=True)
def qu_kb_documents(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"items": list_bindable_documents()})


def _kb_validation_error(exc: Exception) -> JsonResponse:
    return JsonResponse(
        {
            "error": "validation_error",
            "details": {"request": [str(exc)]},
        },
        status=400,
    )


@require_http_methods(["GET", "POST"])
@require_permissions(PERM_KB_ADMIN, api=True)
def knowledge_bases(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse({"items": list_knowledge_bases()})
    try:
        body = json.loads(request.body or b"{}")
        if not isinstance(body, Mapping):
            raise KnowledgeBaseError("Request body must be a JSON object")
        name = body.get("name")
        if not isinstance(name, str):
            raise KnowledgeBaseError("name must be a string")
        scope = body.get("scope", "contact_center")
        description = body.get("description", "")
        if not isinstance(scope, str) or not isinstance(description, str):
            raise KnowledgeBaseError("scope and description must be strings")
        created = create_knowledge_base(
            name=name,
            scope=scope,
            description=description,
            username=request.user.get_username(),
        )
    except json.JSONDecodeError:
        return _kb_validation_error(
            KnowledgeBaseError("Request body must be valid JSON")
        )
    except KnowledgeBaseError as exc:
        return _kb_validation_error(exc)
    return JsonResponse(created, status=201)


@require_http_methods(["GET", "DELETE"])
@require_permissions(PERM_KB_ADMIN, api=True)
def knowledge_base_detail(
    request: HttpRequest,
    kb_id: int,
) -> JsonResponse:
    try:
        if request.method == "DELETE":
            delete_knowledge_base(kb_id)
            return JsonResponse({"ok": True})
        return JsonResponse(get_knowledge_base(kb_id))
    except ContactCenterKnowledgeBase.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)
    except KnowledgeBaseError as exc:
        return _kb_validation_error(exc)


@require_http_methods(["POST"])
@require_permissions(PERM_KB_ADMIN, api=True)
def knowledge_base_upload(
    request: HttpRequest,
    kb_id: int,
) -> JsonResponse:
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return _kb_validation_error(KnowledgeBaseError("file is required"))
    try:
        result = upload_document(
            kb_id,
            filename=uploaded.name,
            content_type=getattr(uploaded, "content_type", "") or "",
            data=uploaded.read(),
            username=request.user.get_username(),
            reindex=True,
        )
    except ContactCenterKnowledgeBase.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)
    except KnowledgeBaseError as exc:
        return _kb_validation_error(exc)
    return JsonResponse(result, status=201)


@require_http_methods(["DELETE"])
@require_permissions(PERM_KB_ADMIN, api=True)
def knowledge_base_document_detail(
    request: HttpRequest,
    kb_id: int,
    document_id: int,
) -> JsonResponse:
    from hub.models import KnowledgeBaseDocument

    try:
        result = delete_document(kb_id, document_id)
    except ContactCenterKnowledgeBase.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)
    except KnowledgeBaseDocument.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)
    except KnowledgeBaseError as exc:
        return _kb_validation_error(exc)
    return JsonResponse(result)


@require_http_methods(["POST"])
@require_permissions(PERM_KB_ADMIN, api=True)
def knowledge_base_reindex(
    request: HttpRequest,
    kb_id: int,
) -> JsonResponse:
    try:
        result = reindex_knowledge_base(kb_id)
    except ContactCenterKnowledgeBase.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)
    except KnowledgeBaseError as exc:
        return _kb_validation_error(exc)
    return JsonResponse(result)


ASSISTANT_ADMIN_PERMS = (
    PERM_ASSISTANT_ADMIN,
    PERM_PROMPTS_ADMIN,
    PERM_KB_ADMIN,
)


def _assistant_validation_error(exc: Exception) -> JsonResponse:
    return JsonResponse(
        {
            "error": "validation_error",
            "details": {"request": [str(exc)]},
        },
        status=400,
    )


def _parse_json_object(request: HttpRequest) -> Mapping[str, Any]:
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise AssistantAdminError("Request body must be valid JSON") from exc
    if not isinstance(body, Mapping):
        raise AssistantAdminError("Request body must be a JSON object")
    return body


@require_http_methods(["GET", "POST"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_knowledge_bases(request: HttpRequest) -> JsonResponse:
    """assistant_* KB namespace — isolated from cc_production."""
    if request.method == "GET":
        return JsonResponse(
            {
                "items": list_assistant_kbs(),
                "namespace": "assistant_*",
                "isolated_from": "cc_production",
            }
        )
    try:
        body = _parse_json_object(request)
        created = create_assistant_kb(
            body,
            username=request.user.get_username(),
        )
    except AssistantAdminError as exc:
        return _assistant_validation_error(exc)
    return JsonResponse(created, status=201)


@require_http_methods(["GET", "DELETE", "PATCH"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_knowledge_base_detail(
    request: HttpRequest,
    kb_id: int,
) -> JsonResponse:
    try:
        if request.method == "DELETE":
            delete_assistant_kb(kb_id)
            return JsonResponse({"ok": True})
        if request.method == "PATCH":
            from hub.website_crawl import apply_website_settings
            from hub.models import AssistantKnowledgeBase

            body = _parse_json_object(request)
            kb = AssistantKnowledgeBase.objects.get(pk=kb_id)
            apply_website_settings(kb, body)
            kb.save()
            return JsonResponse(get_assistant_kb(kb_id))
        return JsonResponse(get_assistant_kb(kb_id))
    except AssistantKnowledgeBase.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)
    except AssistantAdminError as exc:
        if str(exc) in {"KB not found", "document not found"}:
            return JsonResponse({"error": "not_found"}, status=404)
        return _assistant_validation_error(exc)


@require_http_methods(["GET", "POST"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_knowledge_base_crawl(
    request: HttpRequest,
    kb_id: int,
) -> JsonResponse:
    try:
        if request.method == "GET":
            return JsonResponse(get_latest_crawl(kb_id))
        body = _parse_json_object(request)
        result = start_website_crawl(
            kb_id,
            body,
            username=request.user.get_username(),
            request=request,
        )
    except AssistantKnowledgeBase.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)
    except AssistantAdminError as exc:
        if str(exc) == "KB not found":
            return JsonResponse({"error": "not_found"}, status=404)
        return _assistant_validation_error(exc)
    return JsonResponse(result, status=202)


@require_http_methods(["POST"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_knowledge_base_upload(
    request: HttpRequest,
    kb_id: int,
) -> JsonResponse:
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return _assistant_validation_error(
            AssistantAdminError("file is required")
        )
    # Default true for single-file API compat; UI batch upload sends reindex=0.
    reindex_raw = str(
        request.POST.get("reindex")
        if "reindex" in request.POST
        else request.GET.get("reindex") or "1"
    ).strip().lower()
    reindex = reindex_raw not in {"0", "false", "no", "off"}
    try:
        result = upload_assistant_document(
            kb_id,
            filename=uploaded.name,
            content_type=getattr(uploaded, "content_type", "") or "",
            data=uploaded.read(),
            username=request.user.get_username(),
            reindex=reindex,
        )
    except AssistantAdminError as exc:
        if str(exc) == "KB not found":
            return JsonResponse({"error": "not_found"}, status=404)
        return _assistant_validation_error(exc)
    return JsonResponse(result, status=201)


@require_http_methods(["POST"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_knowledge_base_reindex(
    request: HttpRequest,
    kb_id: int,
) -> JsonResponse:
    try:
        return JsonResponse(reindex_assistant_kb(kb_id))
    except AssistantAdminError as exc:
        if str(exc) == "KB not found":
            return JsonResponse({"error": "not_found"}, status=404)
        return _assistant_validation_error(exc)


@require_http_methods(["DELETE"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_knowledge_base_document_detail(
    request: HttpRequest,
    kb_id: int,
    document_id: int,
) -> JsonResponse:
    try:
        return JsonResponse(delete_assistant_document(kb_id, document_id))
    except AssistantAdminError as exc:
        if str(exc) in {"KB not found", "document not found"}:
            return JsonResponse({"error": "not_found"}, status=404)
        return _assistant_validation_error(exc)


@require_http_methods(["GET", "POST"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_prompts(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse({"items": list_prompts()})
    try:
        body = _parse_json_object(request)
        created = create_prompt(body, username=request.user.get_username())
    except AssistantAdminError as exc:
        return _assistant_validation_error(exc)
    return JsonResponse(created, status=201)


@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_prompt_detail(
    request: HttpRequest,
    prompt_id: int,
) -> JsonResponse:
    try:
        if request.method == "GET":
            return JsonResponse(get_prompt(prompt_id))
        if request.method == "DELETE":
            delete_prompt(prompt_id)
            return JsonResponse({"ok": True})
        body = _parse_json_object(request)
        updated = update_prompt(
            prompt_id,
            body,
            username=request.user.get_username(),
        )
    except AssistantAdminError as exc:
        if str(exc) == "prompt not found":
            return JsonResponse({"error": "not_found"}, status=404)
        return _assistant_validation_error(exc)
    return JsonResponse(updated)


@require_http_methods(["GET"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_capabilities(request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        {
            "items": list_capabilities(),
            "note": "VII.5 D4 stub registry — RPA/SQL policies in III.6.5",
        }
    )


@require_http_methods(["GET", "POST"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_skills(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse({"items": list_org_skills()})
    try:
        body = _parse_json_object(request)
        created = create_org_skill(body, username=request.user.get_username())
    except SkillStoreError as exc:
        return _assistant_validation_error(exc)
    except AssistantAdminError as exc:
        return _assistant_validation_error(exc)
    return JsonResponse(created, status=201)


@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_skill_detail(
    request: HttpRequest,
    skill_id: int,
) -> JsonResponse:
    try:
        if request.method == "GET":
            return JsonResponse(serialize_skill(get_org_skill(skill_id)))
        if request.method == "DELETE":
            delete_org_skill(skill_id)
            return JsonResponse({"ok": True})
        body = _parse_json_object(request)
        updated = update_org_skill(
            skill_id,
            body,
            username=request.user.get_username(),
        )
    except SkillNotFound:
        return JsonResponse({"error": "not_found"}, status=404)
    except SkillStoreError as exc:
        return _assistant_validation_error(exc)
    except AssistantAdminError as exc:
        return _assistant_validation_error(exc)
    return JsonResponse(updated)


@require_http_methods(["PATCH", "PUT"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_capability_detail(
    request: HttpRequest,
    code: str,
) -> JsonResponse:
    try:
        body = _parse_json_object(request)
        updated = update_capability(code, body)
    except AssistantAdminError as exc:
        if str(exc) == "capability not found":
            return JsonResponse({"error": "not_found"}, status=404)
        return _assistant_validation_error(exc)
    return JsonResponse(updated)


@require_http_methods(["GET", "POST"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_doc_templates(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse({"items": list_templates()})
    try:
        body = _parse_json_object(request)
        created = create_template(body, username=request.user.get_username())
    except AssistantAdminError as exc:
        return _assistant_validation_error(exc)
    return JsonResponse(created, status=201)


@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_doc_template_detail(
    request: HttpRequest,
    template_id: int,
) -> JsonResponse:
    try:
        if request.method == "GET":
            return JsonResponse(serialize_template(get_template(template_id)))
        if request.method == "DELETE":
            delete_template(template_id)
            return JsonResponse({"ok": True})
        body = _parse_json_object(request)
        updated = update_template(
            template_id,
            body,
            username=request.user.get_username(),
        )
    except AssistantAdminError as exc:
        if str(exc) == "template not found":
            return JsonResponse({"error": "not_found"}, status=404)
        return _assistant_validation_error(exc)
    return JsonResponse(updated)


def _rpa_admin_error(exc: RpaError) -> JsonResponse:
    if str(exc) == "scenario not found":
        return JsonResponse({"error": "not_found"}, status=404)
    return JsonResponse(
        {"error": "validation_error", "details": {"request": [str(exc)]}},
        status=400,
    )


@require_http_methods(["GET", "POST"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_rpa_scenarios(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse({"items": list_rpa_scenarios()})
    try:
        body = _parse_json_object(request)
        created = create_rpa_scenario(body, username=request.user.get_username())
    except RpaError as exc:
        return _rpa_admin_error(exc)
    return JsonResponse(created, status=201)


@require_http_methods(["PATCH", "DELETE"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_rpa_scenario_detail(
    request: HttpRequest,
    scenario_id: int,
) -> JsonResponse:
    try:
        if request.method == "DELETE":
            delete_rpa_scenario(scenario_id)
            return JsonResponse({"ok": True})
        body = _parse_json_object(request)
        updated = update_rpa_scenario(
            scenario_id,
            body,
            username=request.user.get_username(),
        )
    except RpaError as exc:
        return _rpa_admin_error(exc)
    return JsonResponse(updated)


def _sql_access_error(exc: SqlAccessError) -> JsonResponse:
    if str(exc) == "access not found":
        return JsonResponse({"error": "not_found"}, status=404)
    return JsonResponse(
        {"error": "validation_error", "details": {"request": [str(exc)]}},
        status=400,
    )


@require_http_methods(["GET", "POST"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_sql_accesses(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse({"items": list_accesses()})
    try:
        body = _parse_json_object(request)
        created = create_access(body, username=request.user.get_username())
    except SqlAccessError as exc:
        return _sql_access_error(exc)
    return JsonResponse(created, status=201)


@require_http_methods(["PATCH", "DELETE"])
@require_permissions(*ASSISTANT_ADMIN_PERMS, require_all=False, api=True)
def assistant_sql_access_detail(
    request: HttpRequest,
    access_id: int,
) -> JsonResponse:
    try:
        if request.method == "DELETE":
            delete_access(access_id)
            return JsonResponse({"ok": True})
        body = _parse_json_object(request)
        updated = update_access(
            access_id,
            body,
            username=request.user.get_username(),
        )
    except SqlAccessError as exc:
        return _sql_access_error(exc)
    return JsonResponse(updated)


@require_http_methods(["GET", "POST"])
@roles_required(*SUFLER_POLICY_ROLES, api=True)
def dialog_scenarios(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse(list_scenarios())
    try:
        body = _parse_json_object(request)
        created = create_scenario(body, username=request.user.get_username())
    except (AssistantAdminError, ScenarioAdminError, ValueError) as exc:
        return JsonResponse(
            {"error": "validation_error", "details": {"request": [str(exc)]}},
            status=400,
        )
    return JsonResponse(created, status=201)


@require_http_methods(["GET", "PUT"])
@roles_required(*SUFLER_POLICY_ROLES, api=True)
def dialog_scenario_detail(request: HttpRequest, code: str) -> JsonResponse:
    try:
        if request.method == "GET":
            item = get_scenario(code)
            return JsonResponse(serialize_scenario(item, include_graph=True))
        body = _parse_json_object(request)
        publish = bool(body.pop("publish", False)) if isinstance(body, dict) else False
        updated = update_scenario(
            code,
            body,
            username=request.user.get_username(),
            publish=publish,
        )
    except ScenarioAdminError as exc:
        message = str(exc)
        if "not found" in message:
            return JsonResponse({"error": "not_found"}, status=404)
        return JsonResponse(
            {"error": "validation_error", "details": {"request": [message]}},
            status=400,
        )
    except (AssistantAdminError, ValueError) as exc:
        return JsonResponse(
            {"error": "validation_error", "details": {"request": [str(exc)]}},
            status=400,
        )
    return JsonResponse(updated)


@require_http_methods(["POST"])
@roles_required(*SUFLER_POLICY_ROLES, api=True)
def dialog_scenario_test_run(request: HttpRequest, code: str) -> JsonResponse:
    try:
        body = _parse_json_object(request)
        lines = body.get("lines") if isinstance(body, dict) else None
        if not isinstance(lines, list):
            raise ScenarioAdminError("lines must be an array of strings")
        text_lines = [str(item) for item in lines]
        result = run_test_dialog(code, text_lines)
    except ScenarioAdminError as exc:
        message = str(exc)
        if "not found" in message:
            return JsonResponse({"error": "not_found"}, status=404)
        return JsonResponse(
            {"error": "validation_error", "details": {"request": [message]}},
            status=400,
        )
    except (AssistantAdminError, ValueError) as exc:
        return JsonResponse(
            {"error": "validation_error", "details": {"request": [str(exc)]}},
            status=400,
        )
    return JsonResponse(result)


