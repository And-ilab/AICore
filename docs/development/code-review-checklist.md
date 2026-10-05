# Code review checklist — merge to `main`

**Audience:** Human reviewer (required before merge to `main`)  
**Purpose:** Process template for the development team. Copy into the PR review comment (or attach as a filled checklist) and tick items that apply.  
**Out of scope:** This document does **not** instruct bots to run CI, push, merge, or call external services — the reviewer confirms evidence already present on the PR.

| Meta | Fill per PR |
| --- | --- |
| PR | `#____` / link |
| Author | |
| Reviewer | |
| Date | |
| Target branch | `main` |
| Areas touched | ☐ backend ☐ frontend ☐ tests ☐ infra ☐ docs ☐ canvases ☐ other |

**How to use:** mark `[x]` when verified, `[ ]` when pending, `N/A` when the change does not touch that area. Do not merge while any **required** applicable item is unchecked.

---

## 0. PR hygiene (required)

- [ ] Title and description explain **why** (not only what)
- [ ] Linked issue / FR / task id (e.g. `FR-…`, `P…`, acceptance id) when work is contractual
- [ ] Diff scoped — no unrelated refactors or secret dumps
- [ ] No committed secrets (`.env`, keys, tokens, `certs/*.pem`, vault exports)
- [ ] CI on the PR is green **or** failures are explained and waived in writing below

Waive / notes:

```
…
```

---

## 1. Pytest (required when Python / acceptance / migrations change)

Evidence: GitHub Actions job **Pytest** ([`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)) and/or local run.

| Check | Status |
| --- | --- |
| CI `test` (Pytest) green, or equivalent local log attached | ☐ Pass ☐ Fail ☐ N/A |
| New/changed behaviour has unit or integration coverage under `tests/` | ☐ Pass ☐ Fail ☐ N/A |
| Migrations applied cleanly (`manage.py migrate`) — CI step or author note | ☐ Pass ☐ Fail ☐ N/A |
| Acceptance smoke **FR-CC-10** green when CC / chat / sufler paths touched (`acceptance-smoke` job) | ☐ Pass ☐ Fail ☐ N/A |
| Flaky or skipped tests justified in PR | ☐ Pass ☐ Fail ☐ N/A |

Local reference (author may attach output; reviewer does not need to re-run):

```bash
pytest tests -v
# If sufler / chat ARM touched:
pytest -v \
  tests/acceptance/test_suf_t.py::SufTSmokeAcceptanceTest::test_suf_t_01_telephony_hints_after_client_utterance \
  tests/acceptance/test_chat_t.py::ChatTSmokeAcceptanceTest::test_chat_t_04_arm_sufler_hint_with_article_title
```

Reviewer notes:

```
…
```

---

## 2. Lint (required when backend/frontend code changes)

| Check | Status |
| --- | --- |
| CI **Ruff** green (`ruff check backend tests dashboard/app recognizer`) | ☐ Pass ☐ Fail ☐ N/A |
| Frontend: `npm run lint` (oxlint) if `frontend/` changed — CI or author evidence | ☐ Pass ☐ Fail ☐ N/A |
| No new lint suppressions without a one-line justification | ☐ Pass ☐ Fail ☐ N/A |
| Types / obvious style regressions (TS, Django patterns) spot-checked in diff | ☐ Pass ☐ Fail ☐ N/A |

Local reference:

```bash
ruff check backend tests dashboard/app recognizer
cd frontend && npm run lint
```

Reviewer notes:

```
…
```

---

## 3. TZ / FR mapping (required when behaviour is contractual)

Map the PR to ТЗ functional requirements. Primary sources:

| Spec | Path |
| --- | --- |
| AI Hub (umbrella) | [`docs/modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx`](../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx) |
| AI Assistant | [`docs/modules/ai-assistant/`](../modules/ai-assistant/) |
| Integrations (СУЗ, Oktell, chat) | [`docs/integration/`](../integration/) |
| Model / KPI registry comments | [`backend/config/model_registry.yaml`](../../backend/config/model_registry.yaml) |

| Check | Status |
| --- | --- |
| PR lists affected **FR-… / UC-… / INT-… / SUF-T / CHAT-T** ids (or explicitly “non-contractual / chore”) | ☐ Pass ☐ Fail ☐ N/A |
| Implementation matches the cited FR intent (not a silent scope cut) | ☐ Pass ☐ Fail ☐ N/A |
| Docs / OpenAPI / runbooks updated when the contract surface changed | ☐ Pass ☐ Fail ☐ N/A |
| Acceptance or benchmark ids updated if gates changed | ☐ Pass ☐ Fail ☐ N/A |
| Customer-facing copy / error texts align with ТЗ language where required | ☐ Pass ☐ Fail ☐ N/A |

**FR mapping table (fill per PR):**

| FR / UC / test id | Change in this PR | Covered by test? |
| --- | --- | --- |
| e.g. `FR-CC-10` | … | ☐ yes ☐ no ☐ N/A |
| | | |
| | | |

Reviewer notes:

```
…
```

---

## 4. Security (required for all merges; deepen when auth/data/infra touched)

| Check | Status |
| --- | --- |
| No secrets, credentials, or private keys in the diff | ☐ Pass ☐ Fail |
| AuthZ / RBAC: new endpoints use existing decorators / path policies; no accidental public routes | ☐ Pass ☐ Fail ☐ N/A |
| User or tenant input validated; no raw SQL / unsafe shell with request data | ☐ Pass ☐ Fail ☐ N/A |
| SSRF / open redirects / path traversal considered for new URL or file handling | ☐ Pass ☐ Fail ☐ N/A |
| Audit / KUMA sinks not weakened (`AUDIT_*`); sensitive fields not logged in plaintext | ☐ Pass ☐ Fail ☐ N/A |
| Dependency bumps reviewed (lockfile); no unexplained major upgrades | ☐ Pass ☐ Fail ☐ N/A |
| Infra: Compose ports, TLS, and `.env.example` stay safe (no published DB on TEST patterns broken) | ☐ Pass ☐ Fail ☐ N/A |
| HMAC / LDAP / webhook secrets remain env-only | ☐ Pass ☐ Fail ☐ N/A |

Reviewer notes:

```
…
```

---

## 5. UI / canvas parity (required when UI or `canvases/` change)

Sources of truth: markdown specs under [`docs/ui/`](../ui/), interactive mocks in [`canvases/`](../../canvases/), product code in `frontend/`.

| Check | Status |
| --- | --- |
| Changed screens identified vs canvas / `docs/ui/*` mockup | ☐ Pass ☐ Fail ☐ N/A |
| Layout, states (empty / loading / error / success), and RBAC roles match the mockup intent | ☐ Pass ☐ Fail ☐ N/A |
| Copy and key controls (FAB, tabs, ARM vs Hub) match spec — no silent UX regression | ☐ Pass ☐ Fail ☐ N/A |
| If canvas updated: product UI (or Storybook) updated in the same PR **or** follow-up issue linked | ☐ Pass ☐ Fail ☐ N/A |
| If product UI updated: canvas / `docs/ui` updated **or** intentional divergence documented | ☐ Pass ☐ Fail ☐ N/A |
| CI **UI visual (P8-09)** green when canvas-registry / visual baselines affected; baseline PNG updates reviewed | ☐ Pass ☐ Fail ☐ N/A |

Canvas registry (tick those touched):

- [ ] `ai-hub-panel-mockup`
- [ ] `ai-assistant-ui-mockup`
- [ ] `ai-hub-settings-mockup`
- [ ] `online-chat-mockups`
- [ ] `ocr-documents-mockup`
- [ ] `sufer-phone-mockup`
- [ ] `tray-launcher-mockup`
- [ ] `internal-user-kc-mockup`
- [ ] other: _______________

Local reference (author evidence):

```bash
cd frontend
npm run lint
npm run test:visual:canvas    # P8-09 canvas-registry
```

Reviewer notes:

```
…
```

---

## 6. Docs & ops (when applicable)

- [ ] `README` / module README / OpenAPI / Postman updated if API changed
- [ ] Runbook impact considered (deploy, reindex, auth, KUMA) — link or N/A
- [ ] TEST observability / health / metrics paths unchanged or documented

---

## 7. Decision

| Outcome | Tick one |
| --- | --- |
| **Approve** — ready to merge to `main` | ☐ |
| **Request changes** — see notes above | ☐ |
| **Approve with follow-ups** — issues linked: _______________ | ☐ |

Reviewer signature: _________________ date: _________

---

## Quick copy-paste (PR comment)

```markdown
### Code review checklist (`docs/development/code-review-checklist.md`)

**PR:** #
**Reviewer:**

- [ ] 0 Hygiene
- [ ] 1 Pytest (CI / coverage / FR-CC-10 as applicable)
- [ ] 2 Lint (Ruff / oxlint as applicable)
- [ ] 3 TZ FR mapping (table filled or chore/N/A)
- [ ] 4 Security
- [ ] 5 UI / canvas parity (or N/A)
- [ ] 6 Docs & ops (or N/A)

**Decision:** Approve | Request changes | Approve with follow-ups
**Notes:**
```

---

## Related

- CI: [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
- Frontend visual: [`frontend/README.md`](../../frontend/README.md)
- Acceptance: [`tests/acceptance/README.md`](../../tests/acceptance/README.md)
- TZ index: [`docs/README.md`](../README.md)
