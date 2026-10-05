# Training outline — Users (≥5)

**Deliverable type:** slide deck outline only (customer training, этап 5 / VII.3)  
**Audience:** ≥ **5** end users (операторы телефонии / онлайн-чата, пользователи ассистента, пользователи OCR; опционально аналитик — overview)  
**Duration guidance:** 0,5–1 день = **~35–45 слайдов** + 3 practice drills  
**Product:** AI Hub / Суфлёр · договор № 14-03/2026  
**Related:** [РЭ](../delivery/re.md) · [admin-guide-outline.md](admin-guide-outline.md)

> Slide outline only — no full speaker notes. Admins train separately ([admin-guide-outline](admin-guide-outline.md)).

---

## Slide budget

| Block | Module | Slides (guide) | Practice |
| --- | --- | ---: | --- |
| 0 | Opening / roles / do-no-harm | 4–5 | — |
| 1 | Portal & AI Hub launcher | 4–5 | 10 min |
| 2 | Contact Center — telephony sufler | 8–10 | 25 min |
| 3 | Contact Center — online chat ARM | 8–10 | 25 min |
| 4 | Assistant (end user) | 6–8 | 20 min |
| 5 | OCR (end user) | 5–6 | 15 min |
| 6 | Incidents & close | 4–5 | checklist |
| | **Total** | **≈35–45** | **≈1,5 ч drills** |

Can run as two cohorts (CC operators vs Assistant/OCR) if ≥5 seats split by role — keep shared blocks 0–1 and 6.

---

## 0. Opening

| # | Slide title | Learning objective |
| --- | --- | --- |
| 0.1 | Title · why AI Hub in the bank | State purpose: help operator, not replace them |
| 0.2 | Agenda for users (≥5 seats) | Know which blocks apply to own role |
| 0.3 | Roles today: telephony / chat / assistant / OCR | Self-identify module(s) |
| 0.4 | Golden rules | Never auto-send LLM text to client; verify before use; no PDn in TEST chats |
| 0.5 | How to get help (superuser / admin / ИТ) | Name escalation path |

---

## 1. Portal & launcher

**Module coverage:** I.5 portal, windows Суфлёр / Ассистент  

| # | Slide title | Learning objective |
| --- | --- | --- |
| 1.1 | Enter bank portal → AI Hub button | Open launcher |
| 1.2 | Menu: Суфлёр \| Ассистент | Open the right window for the task |
| 1.3 | Window controls (resize / minimize / close) | Manage workspace during call/chat |
| 1.4 | If launcher missing (no rights) | Report RBAC issue — do not share accounts |
| 1.5 | Drill 1 — open both windows (if allowed) | Demonstrate independent windows |

---

## 2. Contact Center — telephony (суфлёр)

**Module coverage:** II.3 operator UX, hints, feedback, ASR awareness  

| # | Slide title | Learning objective |
| --- | --- | --- |
| 2.1 | Place in call flow (Oktell + Hub) | Know when sufler appears on active call |
| 2.2 | Reading a hint card (text · % · source) | Interpret relevance and SUZ title link |
| 2.3 | Expand / copy / use in speech | Use hint without pasting blindly to client |
| 2.4 | Open SUZ article (↗) | Verify source in new tab |
| 2.5 | Feedback buttons (used / incomplete / unused) | Leave feedback every time policy requires |
| 2.6 | No hints / low % — what to do | Fall back to script; notify supervisor |
| 2.7 | ASR indicator basics | Recognize “ASR active” vs silence |
| 2.8 | RU/EN language switch (awareness) | Expect hint language to follow client |
| 2.9 | Drill 2 — TEST call with marked line | Complete one call using ≥1 hint + feedback |
| 2.10 | Telephony user checklist | Pocket card for shift start |

---

## 3. Contact Center — online chat ARM

**Module coverage:** II.4–II.5 operator АРМ, sufler side panel, statuses  

| # | Slide title | Learning objective |
| --- | --- | --- |
| 3.1 | ARM layout: queue · dialogue · client · sufler | Orient three-column workspace |
| 3.2 | Queues & picking a dialogue | Take next / select waiting card |
| 3.3 | Nine operator statuses | Switch status (online / lunch / …) correctly |
| 3.4 | Sufler side panel on client message | Read hint; insert into composer when allowed |
| 3.5 | Composer always available | Type own reply; never rely on auto-send |
| 3.6 | Insert into reply + edit before send | Edit LLM text; then send manually |
| 3.7 | Client card / history / summary (overview) | Find channel history without leaving ARM |
| 3.8 | Colleagues view (if permitted) | Read-only observe; no send |
| 3.9 | Drill 3 — handle one widget dialogue | Reply using hint insert + manual send |
| 3.10 | Chat user checklist | End-of-dialogue steps (category, close) |

---

## 4. Assistant — end user

**Module coverage:** Part III window, sources, tools, feedback  

| # | Slide title | Learning objective |
| --- | --- | --- |
| 4.1 | When to use Assistant (not CC sufler) | Choose module for internal bank Q&A |
| 4.2 | Ask a question · streaming answer | Wait for stream; read full answer |
| 4.3 | Sources block — open citation | Verify against bank document |
| 4.4 | Tools panel (if enabled for role) | Run allowed tool; read status |
| 4.5 | Feedback on answers | Mark useful / incomplete / incorrect |
| 4.6 | What Assistant must not do | No confidential paste into unapproved tools |
| 4.7 | Drill 4 — one HR/ops question with source | Complete Q→answer→open source→feedback |
| 4.8 | Assistant user checklist | |

---

## 5. OCR — end user

**Module coverage:** Part IV user path (not doc-type config)  

| # | Slide title | Learning objective |
| --- | --- | --- |
| 5.1 | Documents tab: queue / upload / review | Navigate OCR sub-tabs |
| 5.2 | Upload allowed formats | Submit pdf/jpg/png per bank rules |
| 5.3 | Review fields & confidence colours | Fix low-confidence fields |
| 5.4 | Approve / export (when allowed) | Complete handoff to downstream |
| 5.5 | Drill 5 — one sample document | Upload → correct one field → approve |
| 5.6 | OCR user checklist | When to escalate to OCR admin |

---

## 6. Incidents, etiquette, close

| # | Slide title | Learning objective |
| --- | --- | --- |
| 6.1 | Common failures (no launcher / empty hints / timeout) | Apply РЭ «аварийные ситуации» |
| 6.2 | Do not share passwords / screens with ПДн | ИБ hygiene |
| 6.3 | Feedback quality = better model over time | Why buttons matter (FR-UND-09 awareness) |
| 6.4 | Cohort sign-off (≥5 users) | Attendance + per-role drill pass |
| 6.5 | Q&A · link to admin owners | Know who changes KB/prompts (not users) |

---

## Recommended drills (users)

| Drill | Role focus | Pass |
| --- | --- | --- |
| 1 | All | Open AI Hub launcher / correct module |
| 2 | Telephony | Hint used + feedback on TEST call |
| 3 | Chat | Insert hint → edit → send; status change |
| 4 | Assistant | Answer with opened source + feedback |
| 5 | OCR | One document reviewed and approved |

Minimum for VII.3: **≥5 users** complete drill 1 plus at least one role-specific drill (2–5).

---

## Optional short tracks (if splitting cohort)

| Track | Blocks | ≈ slides |
| --- | --- | ---: |
| CC only (telephony + chat) | 0–3, 6 | 28–32 |
| Assistant + OCR | 0–1, 4–6 | 22–26 |
| Full mixed (≥5 multi-role) | 0–6 | 35–45 |

---

## Materials to attach later

- Pocket checklists (telephony / chat / assistant / OCR)  
- TEST credentials process (Заказчик AD)  
- Link to user-facing РЭ sections  

**Owner:** Исполнитель (training) · **Approver:** Заказчик (руководители КЦ / подразделений) · **Status:** outline v0.1
