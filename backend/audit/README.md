# Structured audit / KUMA foundation (VI.3)

`backend/audit/` emits one UTF-8 JSON object per security event. The envelope
contains `EventID`, RFC3339 UTC `Timestamp`, device/source fields, subject,
request correlation, result and safe metadata. Request or document bodies,
passwords, prompts and raw customer data are not written.

**P2-05 schema** (`schema_version=1.0` in `schema.py`) is frozen for this
cutover — do not change field names or nesting when wiring KUMA.

VI.3 category codes:

- `authentication`;
- `authorization`;
- `administration`;
- `data_security`;
- `integrations`.

## Sinks

Default development mode writes JSONL to
`backend/var/audit/audit.jsonl`. Docker stores the same file in the persistent
`audit_data` volume.

### Production KUMA collector (VI.3)

```env
AUDIT_ENABLED=true
AUDIT_SINKS=file,kuma
AUDIT_KUMA_COLLECTOR_URL=https://kuma-collector.bank.local/v1/events
AUDIT_HTTP_TIMEOUT_SECONDS=5
```

- `AUDIT_KUMA_COLLECTOR_URL` is preferred; `AUDIT_HTTP_COLLECTOR_URL` is the
  legacy alias.
- Sink name `kuma` equals `http` (same `HttpAuditSink`).
- If `kuma`/`http` is enabled without `file`, **file is auto-enabled** for
  INT-T-AUD-03 local retention.

The collector must return any HTTP 2xx response.

### Fallback when the sink is down

HTTP/KUMA delivery failure does **not** break the business request:

1. The original event remains in the file sink (JSONL).
2. A `hub.integrations.siem_delivery_failure` event is appended locally with
   `failed_event_id` and `error_type`.
3. The application logger records the sink error.

Production rotation and retention of the JSONL file (≥1 year, INT-T-AUD-04)
must be configured by the host/container platform. This package does not
delete or truncate audit files.

Ops smoke: [docs/runbooks/vi3-kuma-audit-smoke.md](../../docs/runbooks/vi3-kuma-audit-smoke.md).

INT-T-AUD samples: `audit.samples.emit_int_t_aud_samples()`.

## Hooks

- Django login success/failure/logout signals;
- `AuditMiddleware` for HTTP 401/403;
- ModelRegistry KB/LLM parameter updates;
- `emit()` and `emit_kb_change()` for future VI.3 actions.
