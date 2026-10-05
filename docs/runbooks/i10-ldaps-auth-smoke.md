# I.10 LDAPS auth smoke (AUTH_BACKEND=ldaps / VII.5 C2)

**Audience:** ops / ДИТ on bank TEST  
**Goal:** replace P2-01 `mock_ldap` with real LDAPS; verify 13 C2 AD groups → I.4 roles.  
**Spec:** [TZ-unified-v1.8%20(МИХ).docx §I.10](../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx) · VII.5.1 C2–C4 · VII.5 №4

## Feature flag

| Value | Backend | When |
| --- | --- | --- |
| `AUTH_BACKEND=mock_ldap` | `MockLDAPBackend` (P2-01) | Local / CI only (`DJANGO_DEBUG=true`) |
| `AUTH_BACKEND=ldaps` | `django_auth_ldap.LDAPBackend` | TEST / PROD (I.10) |

`AUTH_MODE` is a legacy alias (`ldap` → `ldaps`). Prefer `AUTH_BACKEND`.

## C2 matrix (working defaults)

| № | I.4 role code | AD group CN (C2) |
| --- | --- | --- |
| 1 | `software_administrator` | `BB_AI_Software_Admin` |
| 2 | `llm_knowledge_base_administrator` | `BB_AI_LLM_KB_Admin` |
| 3 | `contact_center_module_administrator` | `BB_CC_Module_Admin` |
| 4 | `contact_center_telephony_operator` | `BB_CC_Telephony_Operator` |
| 5 | `contact_center_online_chat_operator` | `BB_CC_Chat_Operator` |
| 6 | `contact_center_internal_user` | `BB_CC_Internal_User` |
| 7 | `contact_center_analyst` | `BB_CC_Analyst` |
| 8 | `ai_assistant_module_administrator` | `BB_AI_Assistant_Admin` |
| 9 | `ai_assistant_user` | `BB_AI_Assistant_User` |
| 10 | `ai_assistant_analyst` | `BB_AI_Assistant_Analyst` |
| 11 | `document_recognition_module_administrator` | `BB_IDP_Admin` |
| 12 | `document_recognition_user` | `BB_IDP_User` |
| 13 | `document_recognition_analyst` | `BB_IDP_Analyst` |

Source: `backend/auth/c2_groups.py` / `RoleDefinition.c2_ad_group`.  
ДИТ may override via `AUTH_LDAP_ROLE_GROUP_MAP_JSON` (role_code → approved CN).

## Prerequisites

1. `pip install -r backend/requirements-ldap.txt` on the Linux app host.
2. Copy [`infra/test/.env.example`](../../infra/test/.env.example) → `infra/test/.env`.
3. Fill C4: `AUTH_LDAP_SERVER_URI=ldaps://…:636`, bind DN/password, user/group bases, CA file.
4. Create the 13 AD groups (or map approved names in JSON) and add a test user to e.g. `BB_CC_Telephony_Operator`.

## Smoke — mapping (no AD needed)

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests\test_ldaps_auth.py tests\test_rbac.py -q
```

**Pass:** all 13 C2 groups resolve to the matching I.4 role; login API returns roles for a user with mirrored AD group.

## Smoke — TEST LDAPS login

```powershell
# After AUTH_BACKEND=ldaps and services restarted:
curl -s -c cookies.txt -X POST http://127.0.0.1:8000/api/auth/login/ `
  -H "Content-Type: application/json" `
  -d "{\"username\":\"test.operator\",\"password\":\"…\"}"

curl -s -b cookies.txt http://127.0.0.1:8000/api/auth/me/
```

**Pass criteria (I.10)**

| Check | Expected |
| --- | --- |
| Backend | `AUTH_BACKEND=ldaps` (not `mock_ldap`) |
| URI | `ldaps://` + trusted CA |
| Login | HTTP 200, `authenticated: true` |
| Roles | Contains I.4 code for the user's AD group (e.g. telephony operator) |
| Tabs | Hub tabs match RBAC for that role |
| Mock | `mock_ldap` auth fails when `DEBUG=false` |

**Rollback:** set `AUTH_BACKEND=mock_ldap` only on non-prod with `DJANGO_DEBUG=true`; never leave mock enabled on bank TEST/PROD.
