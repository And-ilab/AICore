# Customer demo script — AI Hub / Суфлёр (v1.4)

**Audience:** Исполнитель presenter + optional ДИТ operator co-pilot  
**Purpose:** Step-by-step **demo script template** for customer walkthrough of major modules per [ТЗ v1.4](../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx).  
**Contract:** № 14-03/2026 · ОАО «АСБ Беларусбанк**

> **Do not execute a demo automatically.** This file is a checklist/script for a **human** presenter. Do not drive the UI, call bank systems, or start a customer session from CI/bots. Fill stand URL and accounts before the meeting; tick steps live.

| Meta | Fill before demo |
| --- | --- |
| Date / time | |
| Stand | ☐ TEST `https://ai-hub-test.bank.local/` ☐ lab/local ☐ canvas-only |
| Presenter | |
| Customer attendees | |
| Duration budget | ~60–90 min (full) · ~30 min (smoke subset §0) |
| Recording | ☐ yes ☐ no (agree with bank ИБ) |

---

## 0. Prep checklist (day before)

- [ ] Stand healthy: `GET /health/` → 200, `checks.database` + `checks.redis` = `ok`
- [ ] BelVPN / jump works for presenter ([vpn-request-template](vpn-request-template.md))
- [ ] Demo accounts ready (named roles below) — **no shared root**
- [ ] Sample data: ≥1 SUZ article in `cc_production`; sample OCR file; chat widget test page
- [ ] Oktell / telephony: ☐ live TEST line ☐ mock / recorded path (say which)
- [ ] Canvases open as fallback: [`canvases/`](../../canvases/) if stand flaky
- [ ] Golden rules slide ready (see §1)

**Demo accounts (fill):**

| Role | Login | Module |
| --- | --- | --- |
| Telephony operator | | CC суфлёр |
| Chat operator | | Online chat ARM |
| Assistant user | | AI Assistant |
| OCR / IDP verifier | | Documents |
| Admin (KB / Hub) | | Центр настроек |

**Fallback if live path fails:** open the matching Canvas mockup and narrate the same expected outcomes (mark step as *canvas*).

---

## 1. Opening (5 min)

**Goal:** Frame product and do-no-harm rules.

| Step | Action | Expected outcome |
| ---: | --- | --- |
| 1.1 | Introduce AI Hub shell: portal → launcher / FAB | Customer sees bank-branded entry (not a random SaaS) |
| 1.2 | State modules on agenda: **CC telephony · Online chat · Assistant · OCR · Admin** | Agenda agreed |
| 1.3 | State golden rules | (1) LLM text **never** auto-sent to client; (2) operator verifies before use; (3) TEST data only — no real ПДн |
| 1.4 | Point to ТЗ map | Part II КЦ · III Ассистент · IV OCR · I.5–I.6 Hub/Admin |

**Acceptance anchors (narrate, do not run pytest live unless asked):** SUF-T / CHAT-T / ASS-T / DOC-T smoke — [`tests/acceptance/`](../../tests/acceptance/README.md).

---

## 2. Contact Center — telephony суфлёр (12–15 min)

**TZ:** Part II · UC-SUF-T01 · FR-SUF-01/02/06/09 · **SUF-T-01**  
**UI:** standalone суфлёр window (not Hub FAB tabs for telephony operator) · canvas: `sufer-phone-mockup.canvas.tsx` / panel «Суфлёр»

| Step | Action | Expected outcome |
| ---: | --- | --- |
| 2.1 | Login as **telephony operator** | RBAC: суфлёр available; Assistant/OCR Hub tabs absent or blocked per policy |
| 2.2 | Open **standalone** суфлёр window | Separate window (FR-SUF-09) — not only a Hub tab |
| 2.3 | Start / join TEST call (Oktell) **or** mock utterance path | Call/session active; ASR/transcript area live or simulated |
| 2.4 | Produce a **client** utterance (speak or inject test phrase from script bank) | Transcript shows client line (diarization if live) |
| 2.5 | Wait for hints | **3–5** ranked hint cards with relevance % within ~1–2 s (SLA narrative); text from `cc_production` / SUZ |
| 2.6 | Expand one hint; show SUZ title / permalink **to operator only** | Operator sees source; **client channel has no SUZ URL** (SUF-T-04 narrative) |
| 2.7 | Optional: thumbs / feedback on a card | Feedback control visible; no auto-send to caller |
| 2.8 | End call / close session | Session ends cleanly; no leftover auto-messages |

**Pass criteria for demo:** customer sees “client phrase → ranked hints”; presenter states operator must copy/speak manually.

**If Oktell unavailable:** use mock `OKTELL_MODE=mock` / WS fixture and say so explicitly.

---

## 3. Contact Center — online chat (12–15 min)

**TZ:** Part II.4 / II.3.4.2 · **CHAT-T-01**, **CHAT-T-04**  
**UI:** Chat widget + operator ARM · canvas: `online-chat-mockups.canvas.tsx`

| Step | Action | Expected outcome |
| ---: | --- | --- |
| 3.1 | Open **client widget** (test page) | Widget loads; dialog can start |
| 3.2 | Client sends a banking question | Message appears in operator **ARM inbox** (CHAT-T-01) |
| 3.3 | Login as **chat operator**; open dialog | ARM shows thread; skill/queue labels if configured |
| 3.4 | Show **суфлёр hint** in ARM for the client message | Hint card with **article title** from SUZ/KB (CHAT-T-04) |
| 3.5 | Demonstrate insert-to-reply **manual** action (or “copy then paste”) | Text enters reply field **only** after operator action — not auto-sent |
| 3.6 | Optional: send operator reply to widget | Client sees operator text only (not raw internal scores) |
| 3.7 | Close / transfer note | Lifecycle clear; no silent LLM send |

**Pass criteria:** widget → ARM → hint with article title → human-controlled reply.

---

## 4. AI Assistant (10–12 min)

**TZ:** Part III · **ASS-T-01** (login + chat) · FR-ASS-*  
**UI:** Hub panel tab «Ассистент» · canvas: `ai-assistant-ui-mockup.canvas.tsx`, `ai-hub-panel-mockup.canvas.tsx`

| Step | Action | Expected outcome |
| ---: | --- | --- |
| 4.1 | Login as **assistant user** (AD-mapped role) | Session OK; Assistant tab visible |
| 4.2 | Open Hub FAB → **Ассистент** | Chat UI: KB select, new dialog, history |
| 4.3 | Select allowed knowledge base | KB picker shows permitted bases only |
| 4.4 | Ask a grounded question (prepared prompt) | Streaming or final answer; citations/sources if enabled |
| 4.5 | Show empty / error / streaming states (or canvas switcher) | States match mockup (loading, error recoverable) |
| 4.6 | Start **+ Новый** dialog | Clean thread; previous history retained separately |
| 4.7 | Note tools (if demoing RPA/doc) — optional | Tool call visible; no unexpected side effects on TEST |

**Pass criteria:** authenticated user gets an in-policy assistant answer; RBAC hides CC-only surfaces.

---

## 5. OCR / Documents (8–10 min)

**TZ:** Part IV · **DOC-T-01**, **DOC-T-04**  
**UI:** Hub tab «Документы» · canvas: `ocr-documents-mockup.canvas.tsx`

| Step | Action | Expected outcome |
| ---: | --- | --- |
| 5.1 | Login as **OCR / IDP** role | Documents tab visible |
| 5.2 | Open **Документы**; choose document type | Type list from admin config |
| 5.3 | Upload sample file (web upload) | Job created / status “processing” (DOC-T-01) |
| 5.4 | Open result / fields form | Extracted fields shown for review |
| 5.5 | Clear a required field → try confirm | Validation blocks incomplete required set (DOC-T-04) |
| 5.6 | Fill required fields → confirm / export path | Success state; export option if in scope for demo |

**Pass criteria:** upload → job → field review → required-field validation demonstrated.

---

## 6. Admin — Центр настроек (10–12 min)

**TZ:** I.5–I.6 · Admin roles §2.4 · UI [`docs/ui/ai-hub-settings-mockup.md`](../ui/ai-hub-settings-mockup.md)  
**UI:** `/ai-hub/admin` · canvas: `ai-hub-settings-mockup.canvas.tsx`

| Step | Action | Expected outcome |
| ---: | --- | --- |
| 6.1 | From Hub ≡ → **Центр настроек** | Full-screen admin shell with sidebar |
| 6.2 | Show RBAC: switch demo role **or** login as KB admin | Sidebar groups match role (Assistant / КЦ / OCR) |
| 6.3 | **Ассистент → Конфигурация LLM** (landing) | Dashboard of layers (params, prompts, KB, QU…) |
| 6.4 | Open **Параметры модели** — note `assistant_bank` vs `sufler_cc` are separate | Two presets not mixed |
| 6.5 | **СУФЛЁР / КЦ → Редактор сценариев** (read-only walk) | Scenario list / map; not under “Внешние системы” |
| 6.6 | Optional: **Тест сценария** screen | Test harness UI visible |
| 6.7 | **Документы → Типы документов** | OCR types admin list |
| 6.8 | Mention ops (do not run destructive ops live): reindex / QU / rollback runbooks | Point to [`docs/runbooks/`](../runbooks/) |

**Pass criteria:** customer sees Admin as Hub settings (not a separate product); CC scenarios live under СУФЛЁР/КЦ.

---

## 7. Optional short integrations (5 min, if time / stand ready)

| Step | Action | Expected outcome |
| ---: | --- | --- |
| 7.1 | Narrate SUZ Model B / webhook (INT-T-SUZ) | Article publish → index path explained |
| 7.2 | Narrate KUMA / audit sink (INT-T-AUD) | Audit events exist; no secret dump on screen |
| 7.3 | Show `/metrics/` or `/health/` for ops | `sufler_health_ok 1` / health JSON ok |

Skip if BelVPN audience is business-only.

---

## 8. Close (5 min)

| Step | Action | Expected outcome |
| ---: | --- | --- |
| 8.1 | Recap modules demoed | CC phone · chat · Assistant · OCR · Admin |
| 8.2 | Recap golden rules | No auto-send; VERIFY; TEST only |
| 8.3 | Next steps | Cutover checklist · training outlines · formal приёмка IDs |
| 8.4 | Q&A / parking lot | Questions logged with owners |

**Handouts (links, not auto-send):**

- ТЗ: [`TZ-unified-v1.8%20(МИХ).docx`](../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx)  
- Training: [`user-guide-outline.md`](../training/user-guide-outline.md) · [`admin-guide-outline.md`](../training/admin-guide-outline.md)  
- TEST results example: [`tests/acceptance/test_env_results.md`](../../tests/acceptance/test_env_results.md)  
- Deploy/access: [`deploy-test.md`](../runbooks/deploy-test.md) · [`vpn-request-template.md`](vpn-request-template.md)

---

## 9. Smoke subset (~30 min)

If time is short, run only:

| # | Module | Steps |
| --- | --- | --- |
| A | Opening | §1 |
| B | Telephony **or** Chat | §2 **or** §3 (pick live path) |
| C | Assistant | §4.1–4.4 |
| D | OCR | §5.1–5.5 |
| E | Admin | §6.1–6.5 |
| F | Close | §8 |

---

## 10. Live tick sheet (copy into meeting notes)

```markdown
### Demo YYYY-MM-DD — tick live

- [ ] 1 Opening + golden rules
- [ ] 2 CC telephony (SUF-T-01 narrative)
- [ ] 3 Online chat (CHAT-T-01/04)
- [ ] 4 Assistant (ASS-T-01)
- [ ] 5 OCR (DOC-T-01/04)
- [ ] 6 Admin Hub settings
- [ ] 7 Integrations (optional)
- [ ] 8 Close / next steps

Stand: _______________
Fallback canvas used: ☐ no ☐ yes (which: _______________)
Blockers:
```

---

## Related

| Doc | Role |
| --- | --- |
| [`TZ-unified-v1.8%20(МИХ).docx`](../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx) | Contractual scenarios / FR |
| [`docs/ui/`](../ui/) + [`canvases/`](../../canvases/) | Visual fallback |
| [`tests/acceptance/README.md`](../../tests/acceptance/README.md) | Formal IDs (not auto-run in demo) |
| [`code-review-checklist.md`](code-review-checklist.md) | Dev process |
| [`vpn-request-template.md`](vpn-request-template.md) | Access before TEST demo |

**Document owner:** Исполнитель (delivery) · **Action:** human-led demo only — no automated customer presentation.
