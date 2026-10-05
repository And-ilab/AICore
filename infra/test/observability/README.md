# TEST observability baseline

Ops can monitor **TEST uptime** via Prometheus scrape of `/metrics/` and an alert when `/health/` would fail. Structured application/audit logs are aggregated from Compose stdout + audit JSONL (see below).

Customer URL: `https://ai-hub-test.bank.local/` (lab: `https://localhost/`).

## Metrics endpoint

| Item | Value |
| --- | --- |
| Path | **`GET /metrics/`** (Daphne; proxied by edge nginx) |
| Format | Prometheus text exposition (`text/plain; version=0.0.4`) |
| Auth | Public path prefix (restrict scrape to monitoring VLAN / ACL) |
| Dependency | None (`prometheus_client` not required) |

### Series

| Metric | Meaning |
| --- | --- |
| `sufler_up` | Always `1` when the process answers scrapes |
| `sufler_health_ok` | `1` iff `GET /health/` would return HTTP 200 |
| `sufler_health_check{component="database\|redis"}` | Per-dependency probe |

```bash
# Direct (Compose network / local runserver)
curl -sS http://127.0.0.1:8000/metrics/

# Via TEST edge TLS
curl -k -sS https://localhost/metrics/
```

Example body:

```text
# HELP sufler_up Always 1 when the metrics process responds.
# TYPE sufler_up gauge
sufler_up 1
# HELP sufler_health_ok 1 when GET /health/ would return HTTP 200.
# TYPE sufler_health_ok gauge
sufler_health_ok 1
# HELP sufler_health_check Dependency probe (1=ok).
# TYPE sufler_health_check gauge
sufler_health_check{component="database"} 1
sufler_health_check{component="redis"} 1
```

### Scrape stub

See [`prometheus-scrape.yml`](./prometheus-scrape.yml). Point Prometheus (or VictoriaMetrics) at the TEST edge host; use `-k` / bank CA for TLS.

## Alert: `/health/` fail

Stub rule: [`prometheus-alerts.yml`](./prometheus-alerts.yml).

| Alert | Condition | Intent |
| --- | --- | --- |
| `SuflerTestHealthFail` | `sufler_health_ok == 0` for 2m | App reports degraded (db/redis) |
| `SuflerTestTargetDown` | `up{job="sufler-test"} == 0` for 2m | Scrape target unreachable |

Load the rule file into the bank Prometheus / Alertmanager stack (or copy expressions into an existing namespace). Until Alertmanager is wired, ops can poll:

```bash
# Fail → non-zero exit (use in cron / Blackbox / Uptime Kuma)
curl -kf -sS -o /dev/null "https://ai-hub-test.bank.local/health/" \
  || echo "ALERT: TEST /health/ failed"
```

## Structured logging aggregation

TEST Compose already emits logs on stdout/stderr (`./deploy.sh logs`). Audit events are structured JSON (file sink and optional KUMA HTTP).

| Stream | Where | Notes |
| --- | --- | --- |
| Daphne / Django | `docker compose … logs -f backend` | Request errors, ASGI |
| Celery | `… logs -f celery` | Task failures |
| Edge nginx | `… logs -f edge` | Access + TLS errors |
| Audit JSONL | `AUDIT_FILE_PATH` inside backend (see `AUDIT_*` settings) | CEF/JSON for SIEM |
| KUMA | `AUDIT_KUMA_COLLECTOR_URL` when set | Bank SIEM path (VI.3) |

### Aggregation options (stub — pick bank-standard)

1. **Filebeat / Fluent Bit** → ship Compose json-file or journald to ELK / OpenSearch.
2. **Promtail + Loki** → label by `compose_service` (`backend`, `celery`, `edge`).
3. **KUMA / existing SIEM** — prefer audit sink over scraping app logs for compliance events.

Minimal Docker logging driver note (host-side): leave default `json-file` with rotation (`max-size=50m`, `max-file=5`) so disk does not fill on long TEST runs.

### Suggested log fields (app)

When grepping TEST incidents, prefer:

- `request_id` / correlation id (when present)
- `status` / HTTP code
- audit `deviceProduct=AI_Hub`, `source_service`

## Ops checklist

- [ ] Prometheus scrapes `https://<test-host>/metrics/` (or scrape backend:8000 on internal net)
- [ ] Alert rules from `prometheus-alerts.yml` loaded
- [ ] On-call receives `SuflerTestHealthFail` / `SuflerTestTargetDown` (or cron equivalent)
- [ ] Log aggregation destination documented for the TEST VM (ELK/Loki/KUMA)
- [ ] `curl -kf https://…/health/` green after deploy
