# TEST VM — hardware & access request (ДИТ / T+28)

**Status:** READY FOR DIT TICKET · template Исполнителя  
**Contract:** № 14-03/2026 · ОАО «АСБ Беларусбанк»  
**ТЗ:** [VII.3](../../docs/modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx) · Прил.1 §10  
**SLA:** ВМ по требованиям Исполнителя — **T+28 раб. дней** от подписания договора (протокол поручений; ранее «до 18.06» в календарных датах)  
**Full engineering spec:** [`docs/technical/server-requirements.md`](../../docs/technical/server-requirements.md)  
**Env template for this VM:** [`infra/test/.env.example`](./.env.example)  
**Models (dev/test only):** [`model-selection-v1.md`](../../docs/technical/model-selection-v1.md) · `approved_dev` in `backend/config/model_registry.yaml`

> **How to use:** copy sections 1–7 into the ДИТ / service-desk ticket. Do not request production LLM GPU SKUs until measured benchmarks on this TEST VM (prod_candidate remains `null`).

---

## 1. Ticket header (fill before send)

| Field | Value |
| --- | --- |
| Request title | AI Hub / Суфлёр — TEST VM (VII.3), T+28 |
| Requester | ООО «ГС Ритейл» · _TBD contact_ |
| Customer owner (ДИТ) | _TBD_ |
| Environment | **TEST** (not PROD) |
| Hostname (proposed) | `ai-hub-test` / `sufler-test` · _TBD FQDN_ |
| Needed by | **T+28 business days** from contract signature |
| Related | BelVPN for vendor staff (see §6); Bitrix TEST T+30; Oktell TEST line T+45 |

---

## 2. Purpose of the VM

Single bank-hosted TEST server to run the AI Hub Compose stack and joint acceptance:

- SUF-T / CHAT-T / ASS-T / DOC-T / INT-T smoke and integration  
- SUZ (Bitrix) Model B ingest, LDAPS, Oktell TEST line, KUMA audit sink  
- Runtime with **`approved_dev`** model baselines only (stubs + Vosk + E5) — **not** production LLM/ASR capacity (70 streams / 10 RPS)

---

## 3. Hardware baseline (sized for `approved_dev`)

Sizing matches current ModelRegistry **approved_dev** slots (CPU-first). GPU is reserved for optional PoC when leaving stubs — not required to boot TEST.

### 3.1. Compute & memory

| Parameter | **Order (minimum)** | **Recommended (DIT request)** | Rationale (`approved_dev`) |
| --- | --- | --- | --- |
| Platform | VMware VM, **x86_64** | same (Прил.1 §10.1–10.2) | Bank standard |
| vCPU | **8** | **16** | Django/ASGI + Celery + Redis/PG + Vosk ASR (CPU) + E5 embed on ingest |
| RAM | **32 GB** | **64 GB** | OS + containers (~8–12) + PostgreSQL/pgvector + Redis + MinIO + Vosk + `multilingual-e5-large` process + headroom for parallel SUF/CHAT smoke |
| System disk (SSD) | 100 GB | **200 GB** | OS, Docker images, logs |
| Data disk (SSD) | 200 GB | **500 GB** | pgvector indexes, MinIO (OCR/chat), model weights cache, audit ≥90 days |
| GPU | not required for `approved_dev` boot | **1× NVIDIA ≥24 GB VRAM** (optional, attachable) | Only when ДИТ/Исполнитель run non-stub LLM / Paddle OCR PoC on same host; leave **unattached** until PoC approved |
| NIC | 1 Gbit | 1 Gbit+ | Segment routes to AD / Bitrix / Oktell / KUMA |

### 3.2. Disk budget for `approved_dev` artifacts

| Artifact | Approx. size | Slot / note |
| --- | ---: | --- |
| OS + Docker images (app, postgres, redis, minio) | 20–40 GB | Compose stack |
| `vosk-model-small-ru-0.22` (+ optional EN small) | 0.5–2 GB | `asr` · `approved_dev` · **CPU** |
| `intfloat/multilingual-e5-large` weights + cache | 2–4 GB | `embedding` · `approved_dev` · CPU (GPU optional) |
| LLM profiles `stub:sufler_cc` / `stub:assistant_bank` / `stub:docs_ocr` | ~0 | `approved_dev` · no GPU |
| OCR `stub:tesseract` / evaluating Paddle | &lt;1 GB stub; PoC TBD | GPU only if Paddle PoC |
| pgvector `cc_production` + `assistant_*` | tens of GB growth | SUZ corpus dependent |
| MinIO objects + audit JSONL | reserve on data disk | retention ≥90 days logs |

**Do not** size this ticket for PROD 70 concurrent ASR / 2000 assistant users / LLM 10 RPS — that is a separate capacity request after measured benchmarks.

### 3.3. Operating system & runtime

| Item | Requirement |
| --- | --- |
| OS | **Linux x64, not EoL** — **Ubuntu 22.04 or 24.04 LTS** (preferred) or RHEL/Rocky **9** |
| Containers | Docker Engine **24+** + Compose **v2** (or ДИТ-approved equivalent) |
| Python in image | 3.12 (via `backend/Dockerfile`) |
| DB | PostgreSQL **16** + **pgvector** (compose provides) |
| Antivirus | Customer product per §8.10 |
| NTP | Enabled (audit/KUMA timestamps) |
| Internet egress | **Denied by default** (air-gap). Images/models delivered offline / internal registry |

---

## 4. Network & ports (for firewall request)

### 4.1. Publish externally (via bank reverse proxy only)

| Service | Internal | External |
| --- | --- | --- |
| AI Hub UI + API | `:8000` | **HTTPS :443** only |
| MinIO Console | `:9001` | **deny** public; admin jump only |

PostgreSQL `:5432`, Redis `:6379`, MinIO API `:9000` — **internal VLAN only**.

### 4.2. Integrations (open from / to TEST VM)

| Peer | Direction | Proto / port | Needed by |
| --- | --- | --- | --- |
| AD (LDAPS) | VM → AD | TCP **636** + bank CA | I.10 auth |
| Bitrix TEST (СУЗ) | Bitrix → VM webhook; VM → Bitrix `/changes` | HTTPS **443** | Model B / INT-09 · T+30 Bitrix |
| Oktell TEST | bidirectional WS / agreed ports | `wss` / TBD ДИТ | T+45 line |
| KUMA collector | VM → collector | HTTPS | VI.3 audit |
| BelVPN concentrator | vendor laptops → bank | per ЦКБ form | §6 |

Full port matrix: engineering doc §7.

---

## 5. Software stack to install (after VM handoff)

Исполнитель deploys (with ДИТ sudo/Docker as agreed):

1. Clone/release of `sufler`  
2. Copy [`infra/test/.env.example`](./.env.example) → `infra/test/.env` (secrets from vault; never commit)  
3. Deploy **prod-like** stack (not local `infra/docker-compose.yml`):  
   `cd infra/test && ./deploy.sh` → [`docker-compose.prod-like.yml`](./docker-compose.prod-like.yml)  
   (postgres · redis · minio · Daphne backend · celery · nginx frontend)  
4. Health: `GET https://<fqdn>/health/` → HTTP 200, body includes `checks.database` + `checks.redis` = `ok` (nginx → Daphne)  
5. Data tier: `./deploy.sh db-verify` → migrations + `cc_prod_embedding_hnsw_idx` + `verify_data_tier`  
6. Support tier: `./deploy.sh support-verify` → Redis PONG, Celery `sufler.ping`, MinIO put/get  
7. Inference tier: `./deploy.sh inference-verify` → profile=test, ASR + LLM stub, suggest smoke  
8. Cutover when bank ready: [`cutover-checklist.md`](./cutover-checklist.md) (AD → SUZ → Oktell → INT-T)  
9. WebSocket: `wss://<fqdn>/ws/sufler/<call_id>/` (Daphne / Channels)  
10. See [`README.md`](./README.md) for validate/`deploy.sh config` and CI deploy

Optional on VM: Vosk ASR process, offline-copied E5 weights.

---

## 6. BelVPN — vendor remote access (VII.3)

**Fill-in ticket template (BelVPN + VM accounts):** [`docs/development/vpn-request-template.md`](../../docs/development/vpn-request-template.md) — checklist only; do not auto-submit.

| Item | Detail |
| --- | --- |
| What | **BelVPN** (bank remote access) for Исполнитель engineers to reach TEST VM / jump host |
| Who requests | Исполнитель — заявка + list of employees (ФИО, passport/ID per bank form, corporate email, phone) |
| Who approves | **ЦКБ** / ДИТ per bank procedure |
| Timing | BelVPN application historically **T+21** / «до 05.06» in protocol; align with VM **T+28** so access is ready when VM is |
| Scope | Access only to **TEST** segment / agreed jump host — **not** PROD |
| MFA / client | Per bank BelVPN client package; no split-tunnel to Internet for model downloads |
| Accounts on VM | Separate from BelVPN: OS/AD accounts + Docker group — issued by ДИТ after VPN |

**Ticket attachment:** completed BelVPN form (bank template) + this server-requirements file + filled [vpn-request-template](../../docs/development/vpn-request-template.md).

If BelVPN is delayed, temporary supervised on-site / jump-box access must be agreed so T+28 VM is not idle.

---

## 7. Acceptance checklist (ДИТ ↔ Исполнитель)

| # | Check | Owner |
| --- | --- | --- |
| 1 | VM created: **16 vCPU / 64 GB / 200+500 GB SSD**, correct OS | ДИТ |
| 2 | Optional GPU present or explicitly deferred | ДИТ |
| 3 | Docker Engine + Compose installed; Исполнитель can `docker compose ps` | ДИТ + Исполнитель |
| 4 | FQDN + TLS on Compose `edge` (`infra/test/nginx.conf`) or bank proxy → Daphne | ДИТ + Исполнитель |
| 5 | Firewall rules §4.2 in place (AD, Bitrix, Oktell, KUMA) | ДИТ |
| 6 | BelVPN users can reach jump/VM | ЦКБ / ДИТ |
| 7 | `/health/` = 200 with db+redis ok; `./deploy.sh support-verify` (celery + MinIO) | Исполнитель |
| 8 | `deployment_profiles.test` + `./deploy.sh inference-verify` (ASR/LLM stubs; GPU only if vosk/openai PoC) | Исполнитель |

---

## 8. Explicit non-goals (do not put on this ticket)

- PROD HA / second DC  
- GPU sizing for 70 ASR streams or LLM 10 RPS / 2000 concurrent assistants  
- Public Internet for `pip` / HuggingFace  
- Production model sign-off (`prod_candidate` remains null)

Those require a **follow-up capacity ticket** after benchmarks on this TEST VM.

---

## 9. References

| Doc | Role |
| --- | --- |
| [`docs/technical/server-requirements.md`](../../docs/technical/server-requirements.md) | Full DEV/TEST/PROD engineering spec |
| [`docs/technical/model-selection-v1.md`](../../docs/technical/model-selection-v1.md) | `approved_dev` vs production NO-GO |
| [`infra/test/.env.example`](./.env.example) | TEST env (LDAPS, SUZ, Oktell, KUMA) |
| ТЗ v1.4 VII.3 | Training ≥3 admin / ≥5 users; Bitrix T+30; Oktell T+45 |

**Document owner:** Исполнитель (architecture) · **Consumer:** ДИТ · **Version:** 1.0-test-vm-t28
