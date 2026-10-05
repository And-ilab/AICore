# VI.3 KUMA audit smoke (INT-T-AUD)

**Audience:** ops / ИБ on bank TEST  
**Goal:** send P2-05 audit events to the real KUMA HTTP collector; verify INT-T-AUD samples; confirm fallback when collector is down.  
**Spec:** [TZ-unified-v1.8%20(МИХ).docx §VI.3](../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx) · INT-T-AUD-01…04

## Config (prod)

```env
AUDIT_ENABLED=true
AUDIT_SINKS=file,kuma
AUDIT_KUMA_COLLECTOR_URL=https://kuma-collector.bank.local/v1/events
AUDIT_HTTP_TIMEOUT_SECONDS=5
```

| Env | Role |
| --- | --- |
| `AUDIT_KUMA_COLLECTOR_URL` | Preferred VI.3 collector URL |
| `AUDIT_HTTP_COLLECTOR_URL` | Legacy alias (used if KUMA URL empty) |
| `AUDIT_SINKS` | `file` + `kuma` (or `http` — same sink) |

`kuma` is an alias for the HTTP JSON sink. If only `kuma`/`http` is set, **file is auto-enabled** (INT-T-AUD-03 local retention).

Template: [`infra/test/.env.example`](../../infra/test/.env.example).

**P2-05 schema:** `schema_version=1.0` envelope in `backend/audit/schema.py` — **do not change** for this cutover.

## Fallback when KUMA is down (INT-T-AUD-03 / §9.2.6)

1. Business request is **not** aborted.
2. Original event is written to local JSONL (`AUDIT_FILE_PATH` / Docker `audit_data` volume).
3. A follow-up event `hub.integrations.siem_delivery_failure` is appended locally (`failed_event_id`, `error_type`).
4. Application logger records `Audit sink HttpAuditSink failed: …`.

Ops must rotate/retain JSONL ≥1 year (INT-T-AUD-04) via host policy — the package never truncates the file.

## Smoke A — automated INT-T-AUD samples (mock collector)

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests\test_int_t_aud.py tests\test_audit.py -q
```

**Pass:** samples reach mock KUMA with `schema_version=1.0`; collector-down case keeps local event + `siem_delivery_failure`.

## Smoke B — bank TEST collector

1. Set `AUDIT_KUMA_COLLECTOR_URL` to the URL from ДИТ/ИБ; restart backend.
2. Emit samples:

```powershell
$env:DJANGO_SETTINGS_MODULE = "sufler.settings"
$env:PYTHONPATH = "backend"
.\backend\.venv\Scripts\python.exe -c @"
import django
django.setup()
from audit.samples import emit_int_t_aud_samples
events = emit_int_t_aud_samples()
print(len(events), [e.event_type for e in events])
print('schema', {e.schema_version for e in events})
"@
```

3. In KUMA UI / collector logs: confirm EventIDs for login_success, login_failure, logout, access_denied, kb_settings_updated.
4. Temporarily block collector (wrong port / firewall): emit again; confirm JSONL has original + `siem_delivery_failure`.

| ID | Expected |
| --- | --- |
| INT-T-AUD-01 | §9.3 sample types reach collector |
| INT-T-AUD-02 | subject (AD login), Timestamp, result populated |
| INT-T-AUD-03 | KUMA down → local write + failure event |
| INT-T-AUD-04 | JSONL retention policy on host (≥1 year) — ops checklist |

**Rollback:** `AUDIT_SINKS=file` and clear `AUDIT_KUMA_COLLECTOR_URL`; events stay local only.
