# Training outline — Administrators (≥3)

**Deliverable type:** slide deck outline only (customer training, этап 5 / VII.3)  
**Audience:** ≥ **3** administrators (Администратор ПО, Администратор БЗ LLM, Администратор модуля КЦ / ассистента / OCR — по согласованию ролей §2.4)  
**Duration guidance:** 1 день (≈6 ч) = **~45–55 слайдов** + 2–3 лабораторных блока  
**Product:** AI Hub / Суфлёр · договор № 14-03/2026  
**Related:** [РЭ](../delivery/re.md) · [РА](../delivery/ra.md) · [user-guide-outline.md](user-guide-outline.md) · runbooks FR-UND-08

> Не сценарий спикера и не полные слайды — только структура, цели обучения и рекомендуемый объём. Детальный текст/скриншоты — на этапе подготовки презентации.

---

## Slide budget

| Block | Module | Slides (guide) | Hands-on |
| --- | --- | ---: | --- |
| 0 | Opening / agenda / roles | 4–5 | — |
| 1 | Architecture & Admin Hub | 6–8 | 15 min login |
| 2 | Contact Center (CC) admin | 10–12 | 30 min |
| 3 | Assistant admin | 8–10 | 25 min |
| 4 | OCR admin | 6–8 | 20 min |
| 5 | Ops: reindex / QU / rollback | 6–7 | 20 min |
| 6 | ИБ, AD, audit, close | 5–6 | checklist |
| | **Total** | **≈45–55** | **≈2 ч labs** |

Split across 2 half-days if preferred (Day A: Hub+CC+Assistant; Day B: OCR+Ops+ИБ).

---

## 0. Opening

| # | Slide title | Learning objective |
| --- | --- | --- |
| 0.1 | Title · договор · этап обучения VII.3 | Orient to customer training scope |
| 0.2 | Agenda & timing | Know day plan and lab slots |
| 0.3 | Who is “admin” here (≥3 seats) | Map 3+ named attendees to admin role families |
| 0.4 | What users learn separately | Boundary vs [user-guide-outline](user-guide-outline.md) |
| 0.5 | Success criteria for this cohort | List pass checklist (login, reindex, prompt, OCR type, audit view) |

---

## 1. Architecture & Admin Hub

**Module coverage:** оболочка AI Hub, RBAC I.4, Центр настроек  

| # | Slide title | Learning objective |
| --- | --- | --- |
| 1.1 | Contour: Hub · CC · Assistant · OCR · LLM | Name §2.2 modules and what admin owns |
| 1.2 | On-prem / no runtime HTTP to СУЗ | Explain Model B ingest vs CMS |
| 1.3 | Roles matrix (13) — admin subset | Identify own AD group / Hub tabs |
| 1.4 | Login LDAPS vs mock (TEST only) | Use correct auth mode on bank TEST |
| 1.5 | Admin shell: sidebar groups | Navigate ОБЩЕЕ / АССИСТЕНТ / СУФЛЁР·КЦ / ДОКУМЕНТЫ |
| 1.6 | Save footer & change journal | Save settings; know where audit of changes lives |
| 1.7 | Lab A — enter Hub as admin | Complete login → open one admin screen |

---

## 2. Contact Center (CC) — admin

**Module coverage:** КЦ, QU, KB `cc_production`, сценарии, каналы, отчётность  

| # | Slide title | Learning objective |
| --- | --- | --- |
| 2.1 | CC building blocks (QU · суфлёр · чат · отчёты) | Describe admin surfaces for Part II |
| 2.2 | KB КЦ: SUZ → ingest → `cc_production` | Trace content path without runtime SUZ calls |
| 2.3 | Hub «Базы знаний КЦ»: upload / status | Create/upload doc; read index status |
| 2.4 | Reindex trigger (UI + when webhook fails) | Start reindex; know reconcile fallback |
| 2.5 | Модуль понимания: эталоны & `min_relevance` | CRUD эталон; set threshold |
| 2.6 | QU Preview (FR-UND-12) | Run preview; interpret % and matched example |
| 2.7 | Сценарии / промпты КЦ (overview) | Locate scenario editor & bindings |
| 2.8 | Channels & widget configs (admin view) | Know where widget_id / channels are managed |
| 2.9 | CC reports & ASR QA (admin/analyst handoff) | Open reports; know analyst vs admin duty |
| 2.10 | Lab B — reindex + preview | Reindex sample KB → preview known query |
| 2.11 | Pitfalls: empty hints, bad article | Use [reindex](../runbooks/reindex.md) / [rollback-qu](../runbooks/rollback-qu.md) decision tree |
| 2.12 | CC admin checklist | One-page ops checklist for go-live |

---

## 3. Assistant — admin

**Module coverage:** Part III, `assistant_*` KB, prompts, capabilities  

| # | Slide title | Learning objective |
| --- | --- | --- |
| 3.1 | Assistant vs CC isolation | Never mix `assistant_*` with `cc_production` |
| 3.2 | LLM profile `assistant_bank` | Open model params; know fallback concept |
| 3.3 | Prompts library (system/task/scope) | Create/edit prompt; bind KB slug |
| 3.4 | Capabilities / tools toggles | Enable/disable RAG·SQL·… per policy |
| 3.5 | Assistant KB admin | Create assistant KB; upload; isolation check |
| 3.6 | Feedback & reports (FR-RPT-ASS) for admins | Know analyst consumption; what admin monitors |
| 3.7 | Lab C — prompt + preview chat | Change prompt → verify assistant window behaviour |
| 3.8 | Guardrails (ПДн, length, no auto-send) | Enforce bank policies in config |
| 3.9 | Assistant admin checklist | Day-2 ops list |

---

## 4. OCR — admin

**Module coverage:** Part IV, doc types, validation, export  

| # | Slide title | Learning objective |
| --- | --- | --- |
| 4.1 | OCR pipeline overview | Upload → job → fields → approve/export |
| 4.2 | Doc types & required fields | Configure template for a bank form |
| 4.3 | Confidence & pending_review | Interpret low-confidence fields |
| 4.4 | Export gates (`valid` only) | Know when export is blocked |
| 4.5 | Roles: OCR admin vs user | Assign who configures vs who processes |
| 4.6 | Lab D — doc type + sample upload | Define type → process sample → approve |
| 4.7 | OCR admin checklist | Monitoring & escalation |

---

## 5. Ops runbooks (cross-module)

| # | Slide title | Learning objective |
| --- | --- | --- |
| 5.1 | FR-UND-08 chain: reindex → qu_retrain | Explain 60s debounce without developer |
| 5.2 | Runbook: reindex | Follow [reindex.md](../runbooks/reindex.md) verify steps |
| 5.3 | Runbook: qu-retrain | Manual enqueue when auto missed |
| 5.4 | Runbook: rollback-qu | Choose Path 1/2/3 safely |
| 5.5 | Health: `/health/` (db+redis), Celery, Redis | Read Compose health without panic |
| 5.6 | Lab E — dry-run verify suggest | Suggest smoke after reindex |
| 5.7 | When to call Исполнитель / ДИТ | Escalation matrix |

---

## 6. Security, AD, audit, close

| # | Slide title | Learning objective |
| --- | --- | --- |
| 6.1 | AD groups → roles (C2) | Request correct group membership |
| 6.2 | Least privilege for admins | Avoid shared superuser |
| 6.3 | Audit / KUMA (what admins see) | Find audit events; know SIEM handoff |
| 6.4 | Secrets & `.env` (no Git) | Never paste secrets into tickets |
| 6.5 | Cohort sign-off (≥3 admins) | Sign attendance + skill checklist |
| 6.6 | Q&A / next steps (user training) | Hand off to user cohort ≥5 |

---

## Recommended labs (admin)

| Lab | Objective | Pass |
| --- | --- | --- |
| A | Hub login + open Admin | Sees filtered sidebar for role |
| B | Reindex + QU preview | Preview returns ranked docs |
| C | Assistant prompt edit | Chat reflects change |
| D | OCR doc-type sample | Job completes; fields editable |
| E | Suggest after reindex | ≥1 hint + citation |

---

## Materials to attach later (not in this outline)

- Screenshots from Storybook / TEST Hub  
- One-pager checklists (CC / Assistant / OCR)  
- Links: OpenAPI `/api/docs/`, Postman collection, РА/РЭ  

**Owner:** Исполнитель (training) · **Approver:** Заказчик (КЦ / ДРиРИТ) · **Status:** outline v0.1
