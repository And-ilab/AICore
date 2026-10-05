# API documentation (integrators / приёмка)

OpenAPI schema and Postman collection for v1 **assistant**, **sufler**, and
**ingest** (knowledge) APIs.

| Artifact | Path / URL |
|----------|------------|
| Live OpenAPI | `GET /api/schema/` |
| Swagger UI (dev) | `GET /api/docs/` when `DJANGO_DEBUG=true` |
| ReDoc (dev) | `GET /api/redoc/` when `DJANGO_DEBUG=true` |
| Postman Collection v2.1 | [`postman_collection.json`](postman_collection.json) |
| Source schema builder | `backend/api_docs/openapi_v1.py` |

## Import into Postman

1. Postman → **Import** → select `docs/api/postman_collection.json`.
2. Set collection variables if needed:
   - `base_url` — default `http://127.0.0.1:8000`
   - `suz_hmac_signature` — HMAC for SUZ webhook (when secret configured)
   - `access_token` — optional bearer
3. For session-auth endpoints: log in via `POST /api/auth/login/` first
   (cookie `sessionid`), or use mock LDAP `dev-role-*` accounts.

## Regenerate Postman collection

```powershell
cd backend
.\.venv\Scripts\python.exe -m api_docs.export_postman
# → docs/api/postman_collection.json
```

## Covered endpoints

- **assistant:** `POST /api/v1/assistant/chat`, reports catalog/analytics/export/detail
- **sufler:** `POST /api/v1/sufler/suggest`, `POST /api/v1/sufler/test-dialog`
- **ingest:** `POST /api/v1/knowledge/events`, reconcile status/run

Stack: **Django REST Framework** + **drf-spectacular** (curated paths merged via
`POSTPROCESSING_HOOKS`).
