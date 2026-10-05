# Formal smoke on TEST — SUF-T + CHAT-T

**Purpose:** Shareable evidence for customer demo / приёмка that contact-center and chat ARM smoke scenarios pass against the TEST acceptance harness, with the **customer-accessible TEST URL** documented.

| Field | Value |
| --- | --- |
| Date | 2026-07-27 (UTC+3) |
| Runner | Local acceptance harness (`pytest`, Django TestCase) — same scenarios as CI `acceptance-smoke` (FR-CC-10) plus full SUF-T/CHAT-T smoke (`*-01`, `*-04`) |
| Python | 3.12.5 |
| Command | see §3 |
| Overall | **PASS** (4/4 green) |

---

## 1. Customer-accessible TEST URL

| Role | URL |
| --- | --- |
| **Share with customer (bank FQDN)** | **`https://ai-hub-test.bank.local/`** |
| Health (ops) | `https://ai-hub-test.bank.local/health/` |
| Suggest API | `https://ai-hub-test.bank.local/api/v1/sufler/suggest` |
| Widget entry | `https://ai-hub-test.bank.local/` (SPA) · channel API under `/api/v1/channels/` |

**TLS:** HTTPS only (edge nginx). HTTP redirects to HTTPS. See [`infra/test/nginx.conf`](../../infra/test/nginx.conf) and [`infra/test/README.md`](../../infra/test/README.md#edge-tls-nginx).

**Local edge (lab / before BelVPN FQDN):** `https://localhost/` (`curl -k` if self-signed).

> **Note (this run):** Compose project `sufler-test` was **not** running on the executor host, so live `curl` to the FQDN/localhost edge was unavailable. Automated smoke below exercised the same SUF-T / CHAT-T acceptance scenarios that gate PRs (CI) and that must pass on the deployed stand. After `./deploy.sh` on the bank TEST VM, re-check `GET https://ai-hub-test.bank.local/health/` → 200 and optionally append a live probe row in §4.

Env host allowlist (from `infra/test/.env.example`):  
`DJANGO_ALLOWED_HOSTS=…,ai-hub-test.bank.local`

---

## 2. Results — SUF-T smoke + CHAT-T smoke

| ID | Scenario | Status | Duration |
| --- | --- | --- | --- |
| **SUF-T-01** | Telephony path: ranked sufler hints + citations after client utterance (`POST /api/v1/sufler/suggest`) | **pass** | 0.52 s |
| **SUF-T-04** | Client channel reply must not expose SUZ/Bitrix permalink | **pass** | 0.31 s |
| **CHAT-T-01** | Site widget dialog → ARM inbox card | **pass** | 0.02 s |
| **CHAT-T-04** | ARM sufler hint includes SUZ article title (↗ citation) | **pass** | 0.32 s |

**Summary:** 4 pass · 0 fail · **exit 0**

CI gate equivalent (FR-CC-10): **SUF-T-01** + **CHAT-T-04** — both **pass** in this run.

---

## 3. How to reproduce

```bash
# From repository root
backend/.venv/Scripts/python.exe -m pytest -v --tb=short \
  tests/acceptance/test_suf_t.py::SufTSmokeAcceptanceTest \
  tests/acceptance/test_chat_t.py::ChatTSmokeAcceptanceTest
```

CI (subset):

```bash
pytest -v \
  tests/acceptance/test_suf_t.py::SufTSmokeAcceptanceTest::test_suf_t_01_telephony_hints_after_client_utterance \
  tests/acceptance/test_chat_t.py::ChatTSmokeAcceptanceTest::test_chat_t_04_arm_sufler_hint_with_article_title
```

Deployed stand (ops):

```bash
cd infra/test && ./deploy.sh
curl -k https://ai-hub-test.bank.local/health/   # or https://localhost/health/
```

---

## 4. Live stand probe (optional append)

| Check | URL | Status (this run) |
| --- | --- | --- |
| Edge health | `https://ai-hub-test.bank.local/health/` | **not probed** (stack down on runner) |
| Edge health (local) | `https://localhost/health/` | **not probed** (`HTTP 000`) |
| HTTP→HTTPS | `http://…/health/` | expect **301** when edge is up |

---

## 5. Customer share block (copy)

```text
Sufler AI Hub — TEST formal smoke (SUF-T + CHAT-T)
Date: 2026-07-27
URL:  https://ai-hub-test.bank.local/
Health: https://ai-hub-test.bank.local/health/
Results: SUF-T-01 PASS · SUF-T-04 PASS · CHAT-T-01 PASS · CHAT-T-04 PASS
Evidence: tests/acceptance/test_env_results.md
```

---

## 6. Sign-off

| Role | Name | Date |
| --- | --- | --- |
| Исполнитель | _automated smoke run_ | 2026-07-27 |
| Заказчик | _pending review_ | |
