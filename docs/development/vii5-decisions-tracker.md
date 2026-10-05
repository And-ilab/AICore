# VII.5 open decisions tracker (D1–D4+)

**Audience:** PM / architect / customer workshop owners  
**Purpose:** Human **decision tracker** for [ТЗ v1.4 §VII.5.2](../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx) — dependencies that block integration and acceptance.  
**Contract:** № 14-03/2026 · ОАО «АСБ Беларусбанк»

> **Do not decide automatically.** Agents, CI, and scripts must **not** fill Status, Decision, Owner, Deadline, or Signature. Only a named human after workshop / ticket updates this file (or a copy in the project tracker). Blank Decision = still open.

| Meta | Fill |
| --- | --- |
| Tracker owner (Исполнитель) | |
| Customer coordinator (ДРиРИТ) | |
| Last human review | YYYY-MM-DD · name: _______________ |
| Source of truth | [TZ-unified-v1.8%20(МИХ).docx §VII.5](../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx) |

**Status values (use exactly one):** `open` · `workshop_scheduled` · `pending_customer` · `pending_vendor` · `decided` · `blocked` · `deferred`

---

## How to use

1. Copy a row into the meeting notes or keep this file as the living tracker.  
2. Before each workshop: confirm Owner + Deadline.  
3. After a decision: set Status=`decided`, fill **Decision** + **Evidence** (protocol date / ticket) + **Signed by**.  
4. Do **not** mark `decided` from benchmark output alone (see [model-selection-v1.md](../technical/model-selection-v1.md) SIGNOFF).

---

## Core decisions D1–D4

| ID | Topic (ТЗ) | Options / notes | TZ refs | Registry № | Status | Owner | Deadline | Decision (human) | Evidence / ticket | Signed by · date |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **D1** | **Oktell ASR transport:** events + audio path — **MRCP v1/v2 vs WebSocket `phoneevent_*` + dual-leg (модель T)** | A) MRCP RECOGNIZE → NLSML/text · B) Model T WS + dual-leg on-prem ASR · C) Hybrid (T primary, MRCP contingency) | II.2, II.3.4, VI.2 · FR-ASR-18 · [asr-evaluation D1](../benchmarks/asr-evaluation-report.md#открытый-риск-d1-mrcp-vs-websocket--dual-leg) | №1–2 | `open` | ДРиРИТ + вендор Oktell + Исполнитель | _______________ | | | |
| **D2** | **СУЗ (Bitrix):** API / webhook / polling scope and delivery date | A) Webhook Model B · B) API pull · C) Outbox/polling interim · dates vs T+30 Bitrix TEST | V.2, VI.1 | №3 | `open` | ДРиРИТ / подрядчик Bitrix | _______________ | | | |
| **D3** | **KUMA:** platform version, tenant, collector endpoint, event format, EPS | JSON / CEF / Syslog; TCP/UDP/HTTP; test tenant | VI.3 · INT-T-AUD | №5 | `open` | ДРиРИТ / ИБ | _______________ | | | |
| **D4** | **Assistant tools:** RPA, SQL, external sources, image generation — allow / deny / stage | Per [III.6.5](../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx) SQL/code policy; IB air-gap | III.5–III.8 | №8 (related) | `open` | Заказчик (ИБ + owner ассистента) + Исполнитель | _______________ | | | |

### D1 detail checklist (MRCP vs WS)

- [ ] Tech session with Oktell vendor scheduled (date: _______________)  
- [ ] Confirmed whether bank Oktell build supports WS events (vs “событийная модель не поддерживается”)  
- [ ] If MRCP: ports, codec (e.g. G.711), NLSML vs plain text, resource URI documented  
- [ ] If Model T: dual-leg availability **during** call, codec, incremental latency path agreed  
- [ ] Test case for end-to-end p95 ≤1 s (FR-ASR-04) on chosen path — **not** decoder-only bench  
- [ ] Contingency path documented (INT-T-OKTELL-MRCP vs WS smoke)  
- [ ] **Human decision recorded in table above** (not by agent)

### D2 detail checklist (СУЗ)

- [ ] Spec from 04.06 reviewed with Bitrix owner  
- [ ] Event shape (publish / unpublish) and HMAC agreed  
- [ ] SLA: index freshness after change  
- [ ] TEST Bitrix T+30 aligned with decision  
- [ ] **Human decision recorded**

### D3 detail checklist (KUMA)

- [ ] Collector URL / host:port (no secrets in git)  
- [ ] Format + sample event accepted by ИБ  
- [ ] Test tenant / EPS limit  
- [ ] INT-T-AUD smoke path agreed  
- [ ] **Human decision recorded**

### D4 detail checklist (Assistant capabilities)

- [ ] RPA: on / off / allow-list of bots  
- [ ] SQL tool: deny by default vs read-only warehouse  
- [ ] External HTTP sources: allow-list / deny (air-gap)  
- [ ] Image generation: deny unless IB-approved  
- [ ] **Human decision recorded**

---

## Related VII.5.2 rows (optional — same template)

Extend the tracker when workshops cover more than D1–D4:

| ID | Topic | Registry № | Status | Owner | Deadline | Decision | Evidence | Signed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D5 | Online chat: AD login to ARM | II.5.7 / №4 | `open` | ДИТ | | | | |
| D6 | OCR: doc_type, ЭДО, target systems | №8 | `open` | Заказчик | | | | |
| D7 | Unified client history telephony↔chat | №6 | `open` | Заказчик (КЦ) | | | | |
| D8 | Scenario pack ≥50 priority themes | №7 | `open` | Заказчик (КЦ) | | | | |

### Customer data TBD (VII.5.1 C*) — not “decisions” but blockers

| ID | Field | Status | Owner | Deadline | Value received |
| --- | --- | --- | --- | --- | --- |
| C1 | Contacts | `open` | Both | | |
| C2 | 13 AD group names | `open` | ДИТ | | |
| C3 | Extra AD groups | `open` | ДИТ | | |
| C4 | Prod LDAPS host/port/CA | `open` | ДРиРИТ / ИБ | | |

---

## LLM / model vendor (cross-cut — not TZ D2)

**Note:** In ТЗ, **D2 = СУЗ**, not LLM vendor. Production LLM/ASR/OCR **vendor and model** choices are gated in [model-selection-v1.md](../technical/model-selection-v1.md) (SIGNOFF) and VII.5 №9 (KPI methodology). Track here so workshops do not confuse IDs:

| ID | Topic | Options | Status | Owner | Deadline | Decision | Evidence | Signed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **MS-LLM** | Production LLM vendor / on-prem runtime (air-gap) | Stub-only until measured · vendor shortlist · `REJECTED` / `APPROVED_PROD` | `open` | Исполнитель + ДИТ + ИБ | _______________ | | | |
| **MS-ASR** | Production ASR weights (depends on **D1** transport) | See asr-evaluation · no auto pick | `open` | Исполнитель + ДИТ | _______________ | | | |

Rules:

- [ ] No cloud vendor API as automatic fallback  
- [ ] `prod_candidate` stays `null` until human SIGNOFF  
- [ ] Closing **D1** does not auto-approve MS-ASR/MS-LLM  

---

## Workshop log (append-only)

| Date | IDs discussed | Attendees | Outcome | Next action |
| --- | --- | --- | --- | --- |
| | e.g. D1 | | e.g. workshop_scheduled | |
| | | | | |

---

## Copy-paste row (new decision)

```markdown
| ID | Topic | Status | Owner | Deadline | Decision | Evidence | Signed by · date |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D_ | | open | | YYYY-MM-DD | | | |
```

---

## Related

| Doc | Role |
| --- | --- |
| [TZ-unified-v1.8%20(МИХ).docx §VII.5](../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx) | Authoritative D1–D8 + registry №1–9 |
| [model-selection-v1.md](../technical/model-selection-v1.md) | Model/vendor risks + human SIGNOFF |
| [asr-evaluation-report.md](../benchmarks/asr-evaluation-report.md) | D1 MRCP vs WS impact on ASR evidence |
| [oktell-t45-smoke.md](../runbooks/oktell-t45-smoke.md) | WS smoke (MRCP separate contingency) |
| [demo-script.md](demo-script.md) | Do not demo unresolved D1 as “done” |

**Document owner:** Исполнитель · **Updates:** human only after customer/vendor agreement.
