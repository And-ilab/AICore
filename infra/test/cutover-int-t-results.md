# INT-T subset results — TEST cutover

Companion to [`cutover-checklist.md`](./cutover-checklist.md).  
Append a new section for each stand run. Do not put secrets here.

---

## Run 2026-07-27 — local harness (pre-demo automation)

| Field | Value |
| --- | --- |
| Date (UTC+3) | 2026-07-27 |
| Stand | Local developer machine (SQLite / mock integrations) |
| Python | 3.12.5 |
| Command | `pytest -v tests/acceptance/test_int_t.py` |
| Duration | ~2.0 s |
| Flags | `SUZ_INGEST_MODE=mock`, Oktell mock in-process, audit file+HTTP stub |
| Operator | Исполнитель (agent run) |

### Results

| ID | Status | Notes |
| --- | --- | --- |
| INT-T-SUZ-01 | **pass** | First publish webhook → queued → chunks |
| INT-T-SUZ-04 | **pass** | Unpublish soft-deletes target `article_id` |
| INT-T-AUD-01 | **pass** | Samples reach HTTP collector (schema 1.0) |
| INT-T-AUD-04 | **pass** | Local JSONL sink writes |
| INT-T-OKT-01 | **pass** | Mock `phoneevent_ringstarted` + session id |
| INT-T-OKT-04 | **pass** | Suggest citation SUZ title + permalink |
| INT-T-ASR-01 | **pass** | ASR reports catalog reachable |
| INT-T-OKTELL-MRCP-01 | **pass** | Contingency / foundation documented |
| (expand inventory) | skip | `test_expand_ids_are_registered` — expand wave N/A |

**Summary:** 8 pass · 0 fail · 1 skip · **exit 0**

### Live bank checks (this run)

| Check | Status | Notes |
| --- | --- | --- |
| LDAPS I.10 | not run | Requires bank AD — Phase 1 |
| SUZ Bitrix live | not run | Requires Phase 2 HMAC + webhook |
| Oktell T+45 live | not run | Requires Phase 3 `OKTELL_MODE=prod` |
| HTTPS `/health/` | not run | Requires TEST VM edge |

### Sign-off

| Role | Name | Date |
| --- | --- | --- |
| Исполнитель | _automated harness_ | 2026-07-27 |
| Заказчик / ДИТ | _pending demo_ | |

---

## Template — next TEST VM run

```markdown
## Run YYYY-MM-DD — <stand FQDN>

| Field | Value |
| --- | --- |
| Date | |
| Stand | https:// |
| AUTH_BACKEND | |
| SUZ_INGEST_MODE | |
| OKTELL_MODE | |
| Command | pytest -v tests/acceptance/test_int_t.py |

| ID | Status | Notes |
| --- | --- | --- |
| INT-T-SUZ-01 | | |
| INT-T-SUZ-04 | | |
| INT-T-AUD-01 | | |
| INT-T-AUD-04 | | |
| INT-T-OKT-01 | | |
| INT-T-OKT-04 | | |
| INT-T-ASR-01 | | |
| INT-T-OKTELL-MRCP-01 | | |

Live: LDAPS ___ · SUZ ___ · Oktell ___ · /health/ ___
```
