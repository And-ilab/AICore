"""OpenAPI 3 documentation for integrator-facing v1 APIs (приёмка / Postman)."""

from __future__ import annotations

from typing import Any


def build_openapi_v1() -> dict[str, Any]:
    """Curated OpenAPI covering assistant, sufler, ingest, and OCR APIs."""
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Sufler AI Hub API",
            "description": (
                "Integrator-facing OpenAPI for приёмка and Postman. "
                "Covers `/api/v1/assistant` (III.7 / III.10.2), "
                "`/api/v1/sufler` (FR-CC-03 / II.3.5.5), "
                "`/api/v1/knowledge` (SUZ ingest INT-01…09), and "
                "`/api/v1/ocr` (P6-01a, §6.1.4 / §6.1.17)."
            ),
            "version": "1.0.0",
            "contact": {"name": "ООО «ГС Ритейл» · договор № 14-03/2026"},
        },
        "servers": [
            {"url": "http://127.0.0.1:8000", "description": "Local Django"},
            {"url": "/", "description": "Same origin"},
        ],
        "tags": [
            {"name": "assistant", "description": "ИИ-ассистент chat + FR-RPT-ASS"},
            {"name": "sufler", "description": "Суфлёр suggest + internal KC test-dialog"},
            {"name": "ingest", "description": "СУЗ Model B webhook + INT-09 reconcile"},
            {"name": "ocr", "description": "OCR jobs: upload → poll → fields JSON"},
            {
                "name": "telephony",
                "description": "Oktell pickup webhook + dual-leg barge (02*/03*)",
            },
        ],
        "paths": {
            **_assistant_paths(),
            **_sufler_paths(),
            **_ingest_paths(),
            **_ocr_paths(),
            **_telephony_paths(),
        },
        "components": {
            "securitySchemes": {
                "SessionCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "sessionid",
                    "description": "Django session after POST /api/auth/login/",
                },
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Optional bearer token (future / gateway)",
                },
                "SuzHmac": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Sufler-Signature",
                    "description": "HMAC-SHA256(raw_body, SUZ_WEBHOOK_HMAC_SECRET)",
                },
            },
            "schemas": _schemas(),
        },
    }


def _error_responses(*codes: int) -> dict[str, Any]:
    mapping = {
        400: "Validation error",
        401: "Authentication required / HMAC failed",
        403: "Missing RBAC permission",
        404: "Not found",
        409: "OCR result not ready",
        422: "OCR processing error",
        503: "Temporary / misconfigured",
    }
    return {
        str(code): {
            "description": mapping.get(code, "Error"),
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/Error"}
                }
            },
        }
        for code in codes
    }


def _assistant_paths() -> dict[str, Any]:
    session_security = [{"SessionCookie": []}, {"BearerAuth": []}]
    return {
        "/api/v1/assistant/chat": {
            "post": {
                "tags": ["assistant"],
                "operationId": "assistantChatStream",
                "summary": "Stream assistant reply (SSE)",
                "description": (
                    "OpenAI-compatible SSE from ModelGateway profile "
                    "`assistant_bank`. Requires `assistant.use`."
                ),
                "security": session_security,
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/AssistantChatRequest"
                            },
                            "example": {
                                "message": "Нужна справка о вкладе",
                                "session_id": "sess-demo-1",
                                "stream": True,
                            },
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "SSE token stream (text/event-stream)",
                        "headers": {
                            "X-Assistant-Profile": {
                                "schema": {
                                    "type": "string",
                                    "enum": ["assistant_bank"],
                                }
                            },
                            "X-Session-ID": {"schema": {"type": "string"}},
                            "X-Request-ID": {"schema": {"type": "string"}},
                        },
                        "content": {
                            "text/event-stream": {
                                "schema": {"type": "string"}
                            }
                        },
                    },
                    **_error_responses(400, 401, 403),
                },
            }
        },
        "/api/v1/assistant/reports/": {
            "get": {
                "tags": ["assistant"],
                "operationId": "assistantReportsCatalog",
                "summary": "FR-RPT-ASS catalog",
                "security": session_security,
                "responses": {
                    "200": {
                        "description": "Catalog FR-RPT-ASS-01…08",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        },
                    },
                    **_error_responses(403),
                },
            }
        },
        "/api/v1/assistant/reports/analytics/": {
            "get": {
                "tags": ["assistant"],
                "operationId": "assistantReportsAnalytics",
                "summary": "Assistant usage / feedback analytics",
                "security": session_security,
                "parameters": [
                    {
                        "name": "date_from",
                        "in": "query",
                        "schema": {"type": "string", "format": "date"},
                    },
                    {
                        "name": "date_to",
                        "in": "query",
                        "schema": {"type": "string", "format": "date"},
                    },
                    {
                        "name": "department",
                        "in": "query",
                        "schema": {"type": "string"},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Analytics payload",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        },
                    },
                    **_error_responses(400, 403),
                },
            }
        },
        "/api/v1/assistant/reports/export/": {
            "get": {
                "tags": ["assistant"],
                "operationId": "assistantReportsExport",
                "summary": "Export analytics CSV/XLSX (FR-RPT-ASS-07)",
                "security": session_security,
                "parameters": [
                    {
                        "name": "format",
                        "in": "query",
                        "schema": {
                            "type": "string",
                            "enum": ["csv", "xlsx"],
                            "default": "csv",
                        },
                    },
                    {
                        "name": "date_from",
                        "in": "query",
                        "schema": {"type": "string", "format": "date"},
                    },
                    {
                        "name": "date_to",
                        "in": "query",
                        "schema": {"type": "string", "format": "date"},
                    },
                ],
                "responses": {
                    "200": {"description": "CSV or XLSX attachment"},
                    **_error_responses(400, 403),
                },
            }
        },
        "/api/v1/assistant/reports/{report_id}/": {
            "get": {
                "tags": ["assistant"],
                "operationId": "assistantReportDetail",
                "summary": "Single FR-RPT-ASS section",
                "security": session_security,
                "parameters": [
                    {
                        "name": "report_id",
                        "in": "path",
                        "required": True,
                        "schema": {
                            "type": "string",
                            "pattern": "^FR-RPT-ASS-0[1-8]$",
                        },
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Report section payload",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        },
                    },
                    **_error_responses(400, 403),
                },
            }
        },
    }


def _telephony_paths() -> dict[str, Any]:
    pickup = {
        "type": "object",
        "required": ["CallerID", "CalledID", "Idchain"],
        "properties": {
            "CallerID": {"type": "string", "example": "375336664177"},
            "CalledID": {"type": "string", "example": "1001"},
            "Idchain": {"type": "string", "example": "affcc4a7-5bbc-4206-97e2-74d18ba4cb30"},
            "op_name": {"type": "string", "example": "operator1"},
            "call_type": {"type": "string", "enum": ["in", "out"]},
        },
    }
    return {
        "/api/v1/telephony/oktell/call-started": {
            "post": {
                "tags": ["telephony"],
                "operationId": "oktellCallStarted",
                "summary": "Oktell pickup webhook (Подслушивание.pdf)",
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": pickup}},
                },
                "responses": {
                    "201": {"description": "Listeners 02* / 03* started"},
                    **_error_responses(400, 401, 503),
                },
            }
        },
        "/api/v1/telephony/oktell/calls": {
            "get": {
                "tags": ["telephony"],
                "operationId": "oktellCalls",
                "summary": "Active dual-leg listen instances",
                "security": [{"SessionCookie": []}, {"BearerAuth": []}],
                "responses": {
                    "200": {"description": "Active calls"},
                    **_error_responses(401, 403),
                },
            }
        },
    }


def _sufler_paths() -> dict[str, Any]:
    session_security = [{"SessionCookie": []}, {"BearerAuth": []}]
    return {
        "/api/v1/sufler/suggest": {
            "post": {
                "tags": ["sufler"],
                "operationId": "suflerSuggest",
                "summary": "Ranked operator hints (FR-CC-03 / FR-CC-14)",
                "description": (
                    "Requires `sufler.telephony` or `sufler.chat`. "
                    "Returns hints with %% relevance and SUZ citations."
                ),
                "security": session_security,
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/SuflerSuggestRequest"
                            },
                            "example": {
                                "text": "как оформить дебетовую карту",
                                "limit": 3,
                            },
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Hints payload",
                        "headers": {
                            "X-Request-ID": {"schema": {"type": "string"}}
                        },
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/SuflerSuggestResponse"
                                }
                            }
                        },
                    },
                    **_error_responses(400, 401, 403),
                },
            }
        },
        "/api/v1/sufler/scenario/enter": {
            "post": {
                "tags": ["sufler"],
                "operationId": "suflerScenarioEnter",
                "summary": "Enter a suggested scenario from the operator lamp",
                "security": session_security,
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["session_id", "code"],
                                "properties": {
                                    "session_id": {"type": "string"},
                                    "code": {"type": "string"},
                                    "channel": {"type": "string"},
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Active scenario hint",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/SuflerSuggestResponse"
                                }
                            }
                        },
                    },
                    **_error_responses(400, 401, 403),
                },
            }
        },
        "/api/v1/sufler/scenario/exit": {
            "post": {
                "tags": ["sufler"],
                "operationId": "suflerScenarioExit",
                "summary": "Leave the active scenario and return to knowledge base",
                "security": session_security,
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["session_id"],
                                "properties": {"session_id": {"type": "string"}},
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Scenario session cleared",
                        "content": {
                            "application/json": {"schema": {"type": "object"}}
                        },
                    },
                    **_error_responses(400, 401, 403),
                },
            }
        },
        "/api/v1/sufler/test-dialog": {
            "post": {
                "tags": ["sufler"],
                "operationId": "suflerTestDialog",
                "summary": "Internal KC test-dialog (II.3.5.5)",
                "security": session_security,
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/SuflerTestDialogRequest"
                            },
                            "example": {
                                "text": "Какие документы для вклада?",
                                "scenario_id": "CC-SCR-008",
                                "use_pipeline": True,
                            },
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "LLM reply + relevance",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        },
                    },
                    **_error_responses(400, 401, 403),
                },
            }
        },
    }


def _ocr_paths() -> dict[str, Any]:
    session_security = [{"SessionCookie": []}, {"BearerAuth": []}]
    job_id_param = {
        "name": "id",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
        "description": "OCR job_id",
    }
    return {
        "/api/v1/ocr/jobs/": {
            "post": {
                "tags": ["ocr"],
                "operationId": "ocrCreateJob",
                "summary": "Enqueue OCR job (multipart)",
                "description": (
                    "Upload a scan (pdf/jpg/png/tiff). Pass `doc_type` with "
                    "`mode=template`, or `mode=ml` for auto-detect. "
                    "Requires `ocr.use`. Async only — poll GET /jobs/{id}/."
                ),
                "security": session_security,
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "required": ["file"],
                                "properties": {
                                    "file": {
                                        "type": "string",
                                        "format": "binary",
                                    },
                                    "doc_type": {
                                        "type": "string",
                                        "description": "Document type / template id",
                                        "example": "passport",
                                    },
                                    "document_type": {
                                        "type": "string",
                                        "description": "Alias for doc_type",
                                    },
                                    "mode": {
                                        "type": "string",
                                        "enum": ["template", "ml"],
                                        "description": (
                                            "template requires doc_type; "
                                            "ml auto-detects type"
                                        ),
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "202": {
                        "description": "Job queued",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/OcrJobAccepted"
                                }
                            }
                        },
                    },
                    **_error_responses(400, 401, 403),
                },
            }
        },
        "/api/v1/ocr/jobs/{id}/": {
            "get": {
                "tags": ["ocr"],
                "operationId": "ocrGetJob",
                "summary": "OCR job status",
                "description": "status, progress (0–100), error. Requires `ocr.use`.",
                "security": session_security,
                "parameters": [job_id_param],
                "responses": {
                    "200": {
                        "description": "Job metadata",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/OcrJobStatus"
                                }
                            }
                        },
                    },
                    **_error_responses(401, 403, 404),
                },
            }
        },
        "/api/v1/ocr/jobs/{id}/result/": {
            "get": {
                "tags": ["ocr"],
                "operationId": "ocrGetJobResult",
                "summary": "OCR fields JSON",
                "description": (
                    "Structured fields with confidence. "
                    "409 if the job is not completed."
                ),
                "security": session_security,
                "parameters": [job_id_param],
                "responses": {
                    "200": {
                        "description": "Fields + confidence",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/OcrJobResult"
                                }
                            }
                        },
                    },
                    **_error_responses(401, 403, 404, 409, 422),
                },
            }
        },
        "/api/v1/ocr/jobs/{id}/approve/": {
            "post": {
                "tags": ["ocr"],
                "operationId": "ocrApproveJob",
                "summary": "Approve / edit OCR fields (optional stub)",
                "description": (
                    "Optional HITL confirm. Full HITL UI is P6-02. "
                    "Requires `ocr.use`."
                ),
                "security": session_security,
                "parameters": [job_id_param],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/OcrApproveRequest"
                            }
                        }
                    },
                },
                "responses": {
                    "200": {"description": "Approved"},
                    **_error_responses(400, 401, 403, 404, 422),
                },
            }
        },
    }


def _ingest_paths() -> dict[str, Any]:
    return {
        "/api/v1/knowledge/events": {
            "post": {
                "tags": ["ingest"],
                "operationId": "suzKnowledgeEvents",
                "summary": "SUZ Model B webhook (INT-01…05, INT-07)",
                "description": (
                    "HMAC required when `SUZ_WEBHOOK_HMAC_SECRET` is set. "
                    "In `SUZ_INGEST_MODE=prod` the secret is mandatory."
                ),
                "security": [{"SuzHmac": []}],
                "parameters": [
                    {
                        "name": "X-Sufler-Event-Id",
                        "in": "header",
                        "required": False,
                        "schema": {"type": "string"},
                        "description": "Must match body event_id when present",
                    }
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/SuzEventPayload"
                            }
                        }
                    },
                },
                "responses": {
                    "202": {
                        "description": "Accepted and queued",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/SuzEventAccepted"
                                }
                            }
                        },
                    },
                    **_error_responses(400, 401, 503),
                },
            }
        },
        "/api/v1/knowledge/reconcile/": {
            "get": {
                "tags": ["ingest"],
                "operationId": "suzReconcileStatus",
                "summary": "INT-09 reconcile cursor status",
                "responses": {
                    "200": {
                        "description": "Cursor / last run metadata",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        },
                    }
                },
            }
        },
        "/api/v1/knowledge/reconcile/run/": {
            "post": {
                "tags": ["ingest"],
                "operationId": "suzReconcileRun",
                "summary": "Trigger INT-09 Bitrix changes poll",
                "parameters": [
                    {
                        "name": "async",
                        "in": "query",
                        "schema": {
                            "type": "string",
                            "enum": ["0", "1", "true", "false"],
                        },
                        "description": "Queue Celery task when 1/true",
                    }
                ],
                "responses": {
                    "200": {"description": "Synchronous reconcile result"},
                    "202": {"description": "Queued async task"},
                    **_error_responses(403, 502, 503),
                },
            }
        },
    }


def _schemas() -> dict[str, Any]:
    return {
        "Error": {
            "type": "object",
            "required": ["error"],
            "properties": {
                "error": {"type": "string"},
                "details": {"type": "object"},
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "detail": {"type": "string"},
                "required_permissions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "AssistantChatMessage": {
            "type": "object",
            "required": ["role", "content"],
            "properties": {
                "role": {
                    "type": "string",
                    "enum": ["system", "user", "assistant", "tool"],
                },
                "content": {"type": "string"},
            },
        },
        "AssistantChatRequest": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "messages": {
                    "type": "array",
                    "items": {
                        "$ref": "#/components/schemas/AssistantChatMessage"
                    },
                },
                "session_id": {"type": "string"},
                "stream": {"type": "boolean", "default": True},
            },
        },
        "SuflerSuggestRequest": {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string"},
                "query": {
                    "type": "string",
                    "description": "Alias for text",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 3,
                    "default": 3,
                },
            },
        },
        "SuflerCitation": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "permalink": {"type": "string", "format": "uri"},
            },
        },
        "SuflerHint": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "detail_text": {
                    "type": "string",
                    "description": "Fuller KB article for the ⋯ expand on knowledge-base hints.",
                },
                "relevance": {"type": "number"},
                "citations": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/SuflerCitation"},
                },
            },
        },
        "SuflerSuggestResponse": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string", "example": "cc_production"},
                "hints": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/SuflerHint"},
                },
                "request_id": {"type": "string"},
                "latency_ms": {"type": "object"},
                "scenario": {"type": "object", "nullable": True},
                "suggested_scenario": {"type": "object", "nullable": True},
            },
        },
        "SuflerTestDialogRequest": {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string"},
                "scenario_id": {
                    "type": "string",
                    "default": "CC-SCR-008",
                },
                "use_pipeline": {"type": "boolean", "default": True},
            },
        },
        "SuzEventPayload": {
            "type": "object",
            "description": "SUZ Model B event (see ingest README / tz-bitrix-rag)",
            "properties": {
                "event_id": {"type": "string"},
                "event_type": {"type": "string"},
                "article_id": {"type": "integer"},
                "iblock_id": {"type": "integer"},
                "checksum": {"type": "string"},
                "body_plain": {"type": "string"},
                "body_html": {"type": "string"},
            },
        },
        "SuzEventAccepted": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["accepted"]},
                "event_id": {"type": "string"},
                "outcome": {"type": "string", "enum": ["queued"]},
                "task_id": {"type": "string"},
                "ingest_mode": {"type": "string"},
            },
        },
        "OcrJobAccepted": {
            "type": "object",
            "required": ["job_id", "status"],
            "properties": {
                "job_id": {"type": "string"},
                "status": {
                    "type": "string",
                    "example": "queued",
                },
                "progress": {"type": "integer", "minimum": 0, "maximum": 100},
                "document_type": {"type": "string", "nullable": True},
                "mode": {"type": "string", "enum": ["template", "ml"]},
                "message": {"type": "string"},
            },
        },
        "OcrJobStatus": {
            "type": "object",
            "required": ["job_id", "status", "progress"],
            "properties": {
                "job_id": {"type": "string"},
                "status": {"type": "string"},
                "progress": {"type": "integer", "minimum": 0, "maximum": 100},
                "error": {"type": "string", "nullable": True},
                "error_message": {"type": "string", "nullable": True},
                "document_type": {"type": "string", "nullable": True},
                "filename": {"type": "string"},
            },
        },
        "OcrFieldValue": {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
        "OcrJobResult": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "document_type": {"type": "string"},
                "fields": {
                    "type": "object",
                    "additionalProperties": {
                        "$ref": "#/components/schemas/OcrFieldValue"
                    },
                },
                "validation_status": {"type": "string"},
            },
        },
        "OcrApproveRequest": {
            "type": "object",
            "required": ["fields"],
            "properties": {
                "document_type": {"type": "string"},
                "fields": {"type": "object"},
            },
        },
    }


def merge_into_spectacular_schema(
    result: dict[str, Any],
    **_kwargs: Any,
) -> dict[str, Any]:
    """Swagger shows OCR only; other modules stay in the curated export."""
    curated = build_openapi_v1()
    ocr_paths = {
        path: item
        for path, item in curated["paths"].items()
        if path.startswith("/api/v1/ocr")
    }
    result["paths"] = ocr_paths
    result["tags"] = [tag for tag in curated["tags"] if tag.get("name") == "ocr"]

    curated_schemas = curated["components"]["schemas"]
    result["components"] = {
        "securitySchemes": {
            key: value
            for key, value in curated["components"]["securitySchemes"].items()
            if key in {"SessionCookie", "BearerAuth"}
        },
        "schemas": {
            key: value
            for key, value in curated_schemas.items()
            if key == "Error" or key.startswith("Ocr")
        },
    }

    info = result.setdefault("info", {})
    info["title"] = "Sufler OCR API"
    info["description"] = (
        "OCR для интеграторов: загрузка → статус → поля JSON → утверждение. "
        "Остальные модули временно скрыты."
    )
    info.setdefault("version", curated["info"]["version"])
    return result
