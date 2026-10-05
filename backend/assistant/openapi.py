"""OpenAPI 3 document for `/api/v1/assistant` (Part III.7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

OPENAPI_VERSION = "3.0.3"
SCHEMA_PATH = Path(__file__).resolve().parent / "openapi.yaml"


def build_openapi_document() -> dict[str, Any]:
    return {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": "AI Assistant API",
            "description": (
                "Part III.7 REST/SSE and III.10.2 FR-RPT-ASS reports "
                "for the bank assistant. Chat completions stream via "
                "ModelGateway profile `assistant_bank` "
                "(OpenAI-compatible SSE)."
            ),
            "version": "1.0.0",
        },
        "servers": [{"url": "/api/v1/assistant"}],
        "tags": [
            {
                "name": "chat",
                "description": "Streaming chat with assistant_bank",
            },
            {
                "name": "reports",
                "description": "FR-RPT-ASS analytics and CSV/XLSX export (III.10.2)",
            },
            {
                "name": "schema",
                "description": "Machine-readable OpenAPI document",
            },
        ],
        "paths": {
            "/chat": {
                "post": {
                    "tags": ["chat"],
                    "operationId": "assistantChatStream",
                    "summary": "Stream assistant reply (SSE)",
                    "description": (
                        "Accepts a chat turn and streams OpenAI-compatible "
                        "SSE frames (`data: {...}\\n\\n`, final "
                        "`data: [DONE]\\n\\n`) from ModelGateway "
                        "`assistant_bank`."
                    ),
                    "security": [
                        {"SessionCookie": []},
                        {"BearerAuth": []},
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/ChatRequest"
                                },
                                "examples": {
                                    "simple": {
                                        "summary": "Single user message",
                                        "value": {
                                            "message": "Нужна справка о вкладе",
                                            "session_id": "sess-demo-1",
                                            "stream": True,
                                        },
                                    },
                                    "withHistory": {
                                        "summary": "Multi-turn messages",
                                        "value": {
                                            "messages": [
                                                {
                                                    "role": "user",
                                                    "content": "Привет",
                                                },
                                                {
                                                    "role": "assistant",
                                                    "content": "Здравствуйте",
                                                },
                                                {
                                                    "role": "user",
                                                    "content": "Лимит перевода?",
                                                },
                                            ],
                                            "stream": True,
                                        },
                                    },
                                },
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "SSE token stream",
                            "headers": {
                                "X-Assistant-Profile": {
                                    "schema": {
                                        "type": "string",
                                        "enum": ["assistant_bank"],
                                    },
                                    "description": "ModelGateway profile used",
                                },
                                "X-Session-ID": {
                                    "schema": {"type": "string"},
                                },
                                "X-Request-ID": {
                                    "schema": {"type": "string"},
                                },
                            },
                            "content": {
                                "text/event-stream": {
                                    "schema": {
                                        "type": "string",
                                        "description": (
                                            "OpenAI chat.completion.chunk "
                                            "SSE frames"
                                        ),
                                    }
                                }
                            },
                        },
                        "400": {
                            "description": "Validation error",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/Error"
                                    }
                                }
                            },
                        },
                        "401": {
                            "description": "Authentication required",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/Error"
                                    }
                                }
                            },
                        },
                        "403": {
                            "description": "Missing assistant.use permission",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/Error"
                                    }
                                }
                            },
                        },
                    },
                }
            },
            "/reports/": {
                "get": {
                    "tags": ["reports"],
                    "operationId": "assistantReportsCatalog",
                    "summary": "FR-RPT-ASS catalog (III.10.2)",
                    "security": [
                        {"SessionCookie": []},
                        {"BearerAuth": []},
                    ],
                    "responses": {
                        "200": {
                            "description": "Catalog of FR-RPT-ASS-01…08",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"}
                                }
                            },
                        },
                        "403": {
                            "description": "Missing assistant.reports.view",
                        },
                    },
                }
            },
            "/reports/analytics/": {
                "get": {
                    "tags": ["reports"],
                    "operationId": "assistantReportsAnalytics",
                    "summary": "Usage, feedback, and tool-call analytics",
                    "security": [
                        {"SessionCookie": []},
                        {"BearerAuth": []},
                    ],
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
                        {
                            "name": "report_id",
                            "in": "query",
                            "schema": {
                                "type": "string",
                                "pattern": "^FR-RPT-ASS-0[1-8]$",
                            },
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Stub analytics dashboard payload",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"}
                                }
                            },
                        }
                    },
                }
            },
            "/reports/export/": {
                "get": {
                    "tags": ["reports"],
                    "operationId": "assistantReportsExport",
                    "summary": "Export analytics as CSV or XLSX (FR-RPT-ASS-07)",
                    "security": [
                        {"SessionCookie": []},
                        {"BearerAuth": []},
                    ],
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
                        "200": {
                            "description": "CSV or XLSX attachment",
                            "headers": {
                                "X-FR-Catalog": {
                                    "schema": {
                                        "type": "string",
                                        "enum": ["FR-RPT-ASS"],
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/openapi.json": {
                "get": {
                    "tags": ["schema"],
                    "operationId": "assistantOpenApi",
                    "summary": "Fetch generated OpenAPI schema",
                    "responses": {
                        "200": {
                            "description": "OpenAPI 3 document",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"}
                                }
                            },
                        }
                    },
                }
            },
        },
        "components": {
            "securitySchemes": {
                "SessionCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "sessionid",
                },
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                },
            },
            "schemas": {
                "ChatMessage": {
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
                "ChatRequest": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Shorthand single user utterance",
                        },
                        "messages": {
                            "type": "array",
                            "items": {
                                "$ref": "#/components/schemas/ChatMessage"
                            },
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Client session correlation id",
                        },
                        "stream": {
                            "type": "boolean",
                            "default": True,
                            "description": "Must be true (SSE only)",
                        },
                    },
                },
                "Error": {
                    "type": "object",
                    "required": ["error"],
                    "properties": {
                        "error": {"type": "string"},
                        "details": {"type": "object"},
                        "required_permissions": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


def generate_openapi_yaml(path: Path | None = None) -> Path:
    """Write OpenAPI YAML next to this module (or to ``path``)."""
    target = path or SCHEMA_PATH
    document = build_openapi_document()
    target.write_text(
        yaml.safe_dump(
            document,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    return target


if __name__ == "__main__":
    written = generate_openapi_yaml()
    print(f"Wrote {written}")
