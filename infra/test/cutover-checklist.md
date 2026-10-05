# TEST cutover checklist — SUZ / Oktell / AD

**Audience:** Исполнитель + ДИТ on bank TEST VM  
**Goal:** Enable production-shaped endpoints on TEST when bank systems are available; verify with INT-T smoke subset before customer demo.  
**Env template:** [`.env.example`](./.env.example) → `.env` (never commit secrets)

Related runbooks:

- AD / LDAPS: [`docs/runbooks/i10-ldaps-auth-smoke.md`](../../docs/runbooks/i10-ldaps-auth-smoke.md)
- Oktell T+45: [`docs/runbooks/oktell-t45-smoke.md`](../../docs/runbooks/oktell-t45-smoke.md)
- KUMA audit: [`docs/runbooks/vi3-kuma-audit-smoke.md`](../../docs/runbooks/vi3-kuma-audit-smoke.md)
- Stack: [`README.md`](./README.md) · edge TLS · `db-verify` / `support-verify` / `inference-verify`

---

## 1. Feature flags (mock → TEST prod endpoints)

Flip **one integration at a time**. Restart `backend` + `celery-worker` (and `edge` if hosts change) after each change.

| Flag | Safe / local / CI | TEST when bank ready | Notes |
| --- | --- | --- | --- |
| `AUTH_BACKEND` / `AUTH_MODE` | `mock_ldap` | **`ldaps`** | I.10; needs CA + bind + C2 groups |
| `SUZ_INGEST_MODE` | `mock` | **`prod`** | HMAC **required** in prod |
| `SUZ_WEBHOOK_HMAC_SECRET` | empty (mock only) | **vault secret** | Shared with Bitrix |
| `SUZ_RECONCILE_ENABLED` | `false` | **`true`** after Bitrix `/changes` live | INT-09 |
| `BITRIX_REST_BASE_URL` / `BITRIX_SERVICE_TOKEN` | empty / mock | **SUZ TEST URL + token** | |
| `OKTELL_MODE` | `mock` | **`prod`** | T+45 line |
| `OKTELL_ENABLED` | `false` / `true`+mock | **`true`** | |
| `OKTELL_PROD_WS_URL` / `OKTELL_WS_URL` | mock WS | **`wss://…` bank** | |
| `OKTELL_TEST_QUEUE` / `OKTELL_TEST_MARKING` | placeholders | **ДИТ values** | |
| `AUDIT_SINKS` | `file` | `file,kuma` | VI.3 |
| `AUDIT_KUMA_COLLECTOR_URL` | empty | **collector URL** | |
| `AI_INFERENCE_PROFILE` | `test` | `test` | ModelRegistry deployment profile |
| `ASR_MODE` | `stub` | `stub` or `vosk` | GPU only if vosk PoC |
| `MODEL_GATEWAY_MODE` | empty → stub | empty or `openai` | approved candidate only |
| `OCR_OBJECT_STORE_BACKEND` | `fs` / `auto` | **`minio`** | TEST compose default |
| `DJANGO_DEBUG` | `true` local | **`false`** | |

Canonical TEST cutover values are already sketched in `.env.example` (`ldaps`, `SUZ_INGEST_MODE=prod`, `OKTELL_MODE=prod`). Keep **`mock_*`** until the corresponding bank endpoint is reachable.

---

## 2. Ordered cutover steps

### Phase 0 — Stand ready (no bank integrations)

| # | Step | Owner | Done |
| --- | --- | --- | --- |
| 0.1 | VM + BelVPN + Docker (see [`server-requirements.md`](./server-requirements.md)) | ДИТ / Исполнитель | ☐ |
| 0.2 | `cp .env.example .env`; set Postgres/MinIO/Django secrets from vault | Исполнитель | ☐ |
| 0.3 | Until bank ready: set `AUTH_BACKEND=mock_ldap`, `SUZ_INGEST_MODE=mock`, `OKTELL_MODE=mock`, `OKTELL_ENABLED=true` | Исполнитель | ☐ |
| 0.4 | `./gen-self-signed-cert.sh` (or bank certs) → `./deploy.sh` | Исполнитель | ☐ |
| 0.5 | `./deploy.sh db-verify` · `support-verify` · `inference-verify` | Исполнитель | ☐ |
| 0.6 | `curl -k https://<fqdn>/health/` → 200, db+redis ok | Исполнитель | ☐ |

### Phase 1 — Active Directory (I.10)

| # | Step | Owner | Done |
| --- | --- | --- | --- |
| 1.1 | LDAPS reachability `:636` + bank CA on host | ДИТ | ☐ |
| 1.2 | 13 C2 groups (or `AUTH_LDAP_ROLE_GROUP_MAP_JSON`) + test users | ДИТ | ☐ |
| 1.3 | Fill `AUTH_LDAP_*` in `.env`; set `AUTH_BACKEND=ldaps` | Исполнитель | ☐ |
| 1.4 | Restart backend; runbook smoke login + `/api/auth/me/` roles | Исполнитель | ☐ |
| 1.5 | Confirm `mock_ldap` no longer used on TEST | Исполнитель | ☐ |

### Phase 2 — SUZ / Bitrix Model B

| # | Step | Owner | Done |
| --- | --- | --- | --- |
| 2.1 | Webhook URL published: `https://<fqdn>/api/v1/knowledge/events` | ДИТ / Исполнитель | ☐ |
| 2.2 | Shared HMAC in vault → `SUZ_WEBHOOK_HMAC_SECRET`; `SUZ_INGEST_MODE=prod` | Both | ☐ |
| 2.3 | `SUZ_ALLOWED_IBLOCK_IDS` confirmed | Владелец СУЗ | ☐ |
| 2.4 | Bitrix → publish test article; chunks in `cc_production` | Both | ☐ |
| 2.5 | Optional INT-09: `BITRIX_*` + `SUZ_RECONCILE_ENABLED=true` | Both | ☐ |
| 2.6 | Restart backend/celery; Celery sees ingest tasks | Исполнитель | ☐ |

### Phase 3 — Oktell T+45

| # | Step | Owner | Done |
| --- | --- | --- | --- |
| 3.1 | TEST queue/number + marking delivered (OKT-7) | ДИТ | ☐ |
| 3.2 | `OKTELL_MODE=prod`, `OKTELL_ENABLED=true`, `OKTELL_PROD_WS_URL=wss://…`, queue/marking | Исполнитель | ☐ |
| 3.3 | Network path app → Oktell WS | ДИТ | ☐ |
| 3.4 | Runbook smoke B (ringstarted → session); keep mock path documented for rollback | Исполнитель | ☐ |

### Phase 4 — Audit / KUMA (optional before demo)

| # | Step | Owner | Done |
| --- | --- | --- | --- |
| 4.1 | `AUDIT_SINKS=file,kuma` + collector URL | Исполнитель / ДИТ | ☐ |
| 4.2 | VI.3 smoke — events in file + collector | Исполнитель | ☐ |

### Phase 5 — INT-T subset + demo gate

| # | Step | Owner | Done |
| --- | --- | --- | --- |
| 5.1 | Run INT-T smoke subset (§3) | Исполнитель | ☐ |
| 5.2 | Record results in [`cutover-int-t-results.md`](./cutover-int-t-results.md) | Исполнитель | ☐ |
| 5.3 | Update `tests/acceptance/matrix.json` statuses; optional `generate_protocol.py` | Исполнитель | ☐ |
| 5.4 | Demo gate: HTTPS health + LDAPS login + SUZ article hint + Oktell path (or mock if T+45 delayed) | Both | ☐ |

### Rollback (per flag)

| Integration | Rollback flags | Action |
| --- | --- | --- |
| AD | `AUTH_BACKEND=mock_ldap` | Restart backend (dev-only emergency) |
| SUZ | `SUZ_INGEST_MODE=mock`, clear HMAC if needed | Restart; Bitrix pause webhook |
| Oktell | `OKTELL_MODE=mock` + mock WS | Restart; use runbook Smoke A |
| KUMA | `AUDIT_SINKS=file` | Restart |

---

## 3. INT-T subset (pre-demo)

Smoke rule: IDs ending in **`-01`** or **`-04`** (see [`tests/acceptance/README.md`](../../tests/acceptance/README.md)).

### 3.1 Automated (CI / local / TEST app host)

```bash
# From repo root, with backend venv + DJANGO_SETTINGS_MODULE
pytest -v tests/acceptance/test_int_t.py
```

Covered cases:

| ID | What it proves |
| --- | --- |
| **INT-T-SUZ-01** | First publish webhook → queued → `cc_production` |
| **INT-T-SUZ-04** | Unpublish soft-deletes active chunks |
| **INT-T-AUD-01** | Audit samples reach HTTP collector shape |
| **INT-T-AUD-04** | Local JSONL sink writes |
| **INT-T-OKT-01** | Oktell mock ringstarted → session id |
| **INT-T-OKT-04** | Suggest hint citation has SUZ permalink/title |
| **INT-T-ASR-01** | ASR reports catalog reachable |
| **INT-T-OKTELL-MRCP-01** | MRCP foundation marker (smoke) |

Harness also asserts integration smoke ID inventory (`test_int_t_smoke_ids_are_01_or_04`).

### 3.2 Live bank checks (manual, after Phase 1–3)

| ID / check | Command / evidence | Pass criteria |
| --- | --- | --- |
| LDAPS | Runbook I.10 login | `/api/auth/me/` shows C2 role |
| SUZ live | Publish from Bitrix TEST | Chunks + suggest citation |
| Oktell live | T+45 call | ringstarted / session in logs |
| Edge | `curl -k https://<fqdn>/health/` | 200 + db/redis ok |

### 3.3 Out of scope for this subset

Full INT-T-SUZ-02…08, INT-T-OKT-02…07, INT-T-ASR-02…03, INT-T-OKTELL-MRCP-02 — schedule after demo or in EXPAND wave ([`EXPAND.md`](../../tests/acceptance/EXPAND.md)).

---

## 4. Results log

Fill [`cutover-int-t-results.md`](./cutover-int-t-results.md) on each TEST cutover run (date, stand, flags, pass/fail).

---

## 5. Demo-day snapshot (copy)

```text
Stand: https://________________/
AUTH_BACKEND=________  SUZ_INGEST_MODE=________  OKTELL_MODE=________
INT-T subset: pass / fail (see cutover-int-t-results.md)
Health: GET /health/ → ________
Signer Исполнитель: ________  Date: ________
```
