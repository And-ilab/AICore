# Model Selection v1

Статус: **DRAFT / NO-GO for production model sign-off**  
Дата консолидации: 2026-07-20  
Назначение: единый документ P1-61 для ИБ, Заказчика, архитектуры и эксплуатации

## Executive decision

На дату консолидации в `reports/` и `benchmarks/results/` нет measured JSON,
пригодных для production model selection. Реализованные stub suites проверяют
контракты и формат отчётов, но значения `placeholder`, `null` и результаты
synthetic fixtures не являются доказательством KPI.

Итоговое решение v1:

- установить `approved_dev` только для слотов с заданным `dev_model`: ASR,
  embedding и трёх LLM-профилей;
- оставить QU, OCR и reranker в `evaluating`, поскольку их `dev_model=null`;
- сохранить `prod_candidate: null` для каждого слота;
- разрешить текущие dev baselines только для разработки и интеграции;
- сохранить `kb_cc_production` как `dev_frozen` engineering baseline, а не
  measured optimum;
- не утверждать GPU/RAM sizing до benchmark на target test/prod VM;
- optional reranker оставить отключённым и non-blocking;
- все formal sign-off оставить `pending`.

Машиночитаемый source of truth:
[`backend/config/model_registry.yaml`](../../backend/config/model_registry.yaml).

## Per-slot decision

| Slot / profile | Current dev baseline | Production decision | Status | Основное основание |
| --- | --- | --- | --- | --- |
| `asr` | `vosk-model-small-ru-0.22` | `prod_candidate=null` | `approved_dev` | Dev integration approved; нет measured RU/EN WER, 8 kHz, hotword и 70-stream evidence |
| `embedding` | `intfloat/multilingual-e5-large` | `prod_candidate=null`; использовать только frozen dev profile | `approved_dev` | Dev baseline approved; нет measured recall@5 и сравнительного chunk/threshold optimum |
| `qu` | Архитектура hybrid; classifier model `null` | `prod_candidate=null` | `evaluating` | ADR принят, но synonym/bilingual predictions отсутствуют |
| `llm_sufler_cc` | `stub:sufler_cc` | `prod_candidate=null`; stub запрещён в production | `approved_dev` | Dev contract approved; нет measured grounding, hallucination, p95 и 10 RPS |
| `llm_assistant_bank` | `stub:assistant_bank` | `prod_candidate=null`; stub запрещён в production | `approved_dev` | Dev SSE/tool contract approved; model quality/capacity отсутствуют |
| `llm_docs_ocr` | `stub:docs_ocr` | `prod_candidate=null`; stub запрещён в production | `approved_dev` | Dev JSON contract approved; gold field values отсутствуют |
| `ocr` | Model не выбран; PaddleOCR первый PoC, Tesseract baseline | `prod_candidate=null` | `evaluating` | Нет P1-51 files/metrics и FR-OCR-22 evidence |
| `reranker` | `null`; optional | `prod_candidate=null`; skip разрешён | `evaluating` | Cross-encoder отсутствует; A/B marked non-blocking |

Ни одна строка не является production recommendation. Названия dev baseline
не означают, что соответствующая модель победила в сравнении.

`approved_dev` разрешает только dev/test использование текущего immutable
baseline. Этот статус не подтверждает KPI, capacity, ИБ или приёмку Заказчика
и не разрешает P7/P10 production deployment.

## Compute and capacity decision

GPU/RAM нельзя корректно определить по model family без точной revision,
runtime, quantization, batch/concurrency, context length и target hardware.
Поэтому неизвестные значения фиксируются как `TBD measured`, а не
оцениваются из публичных model cards.

| Slot | Current execution class | GPU decision | RAM / VRAM decision | Обязательное evidence |
| --- | --- | --- | --- | --- |
| ASR | Vosk dev может работать на CPU | Production GPU `TBD measured` | RAM `TBD measured` для 70 потоков | 70 concurrent, WER, p95, CPU/RAM/GPU peaks |
| Embedding | E5 dev; CPU/GPU runtime не зафиксирован | `TBD measured` | Index RAM, process RAM и VRAM `TBD measured` | Corpus size, vector dimensions, ingest/query throughput |
| QU | Hybrid embedding + classifier | Classifier GPU `TBD`; embedding shared | RAM/VRAM `TBD measured` | Concurrent inference, retrain, fusion latency |
| LLM `sufler_cc` | Stub only | Accelerator/model topology `TBD` | RAM/VRAM/KV cache `TBD` | 10 RPS ×60 s, p95 ≤2 s, context and concurrency |
| LLM `assistant_bank` | Stub only | Accelerator/model topology `TBD` | 8k context RAM/VRAM `TBD` | SSE, tools, context, user concurrency and load |
| LLM `docs_ocr` | Stub only | Accelerator/model topology `TBD` | Batch/context RAM/VRAM `TBD` | OCR text size distribution, JSON quality and load |
| OCR | Candidate dependent | Tesseract CPU; Paddle/IDP GPU decision `TBD` | RAM/VRAM `TBD measured` | Pages/sec, batch size, image resolution and layout pipeline |
| Reranker | Disabled | No allocation while skipped | No allocation while skipped | A/B gain and added p95 before capacity reservation |

Три LLM-профиля могут использовать общий on-prem endpoint/model, но capacity
нельзя суммировать или разделять до утверждения routing и workload mix.

Перед sign-off каждый hardware report должен содержать:

- VM/bare-metal name и назначение `test`/`prod`;
- CPU model и logical/physical cores;
- RAM;
- GPU model/count, VRAM, driver и runtime;
- container image digest;
- model revision, weights checksum и quantization;
- batch size, context length, concurrency и duration;
- peak CPU/RAM/GPU/VRAM;
- p50/p95/p99, throughput, timeout/OOM/error counts.

## Slot details

### ASR

Decision:

- Vosk остаётся dev integration baseline;
- production model не выбран;
- договорный KPI нормализован как word accuracy ≥90% / WER ≤10%;
- должны быть измерены RU и EN, телефонный 8 kHz, шум, hotword и 70 calls.

Evidence:

- [`asr-candidates.md`](../benchmarks/asr-candidates.md);
- [`asr-evaluation-report.md`](../benchmarks/asr-evaluation-report.md);
- P1-11 `asr_streaming.py`;
- P1-12 `asr_hotword.py`;
- P1-13 `asr_load.py`.

Fallback:

- откат на предыдущую подписанную ASR model/dictionary revision;
- при недоступности ASR не генерировать подсказку из отсутствующего
  транскрипта;
- сохранить звонок/событие по утверждённой политике и показать оператору
  явный degraded status;
- внешний cloud ASR не включать автоматически.

Главные риски: нет реальных dual-leg WAV, MRCP/WS binding не закрыт (**VII.5 D1** — human tracker [`docs/development/vii5-decisions-tracker.md`](../development/vii5-decisions-tracker.md)), model
weights RU/EN не зафиксированы, hardware sizing отсутствует.

### Embedding and `kb_cc_production`

Current dev baseline:

```yaml
embedding_model: intfloat/multilingual-e5-large
chunk_size_tokens: 512
chunk_overlap_tokens: 100
context_inclusion: 0.60
deterministic_answer: 0.85
status: dev_frozen
```

Это engineering baseline для P3-01/P3-04. P1-21/P1-22 evidence в
ModelRegistry равно `null`.

Evidence:

- [`embedding-candidates.md`](../benchmarks/embedding-candidates.md);
- `embedding_recall.py`;
- `chunk_grid.py`;
- `retrieval_thresholds.py`;
- `index_latency.py`;
- `rag_grounding.py`.

Fallback:

- хранить предыдущий подписанный index/model/profile как совместимую версию;
- при неуспешной переиндексации продолжать чтение предыдущего индекса;
- ниже `context_inclusion` выполнять clarification/escalation;
- запрещать ungrounded LLM answer;
- не менять chunk/threshold без repeat benchmark и sign-off.

Главные риски: synthetic 20-document dataset, recall threshold не утверждён,
frozen defaults не измерены, production corpus/index RAM неизвестны.

### Query Understanding

Architecture decision:

- hybrid embedding + classifier + deterministic fusion;
- embedding остаётся mandatory fallback для one-shot intents;
- classifier model и confidence calibration не выбраны;
- top-2 delta ≤5 percentage points ведёт к clarification.

Evidence:

- P1-30 [`qu-architecture.md`](qu-architecture.md);
- P1-31/P1-32
  [`qu-evaluation-report.md`](../benchmarks/qu-evaluation-report.md);
- `qu_synonyms.py`;
- `qu_bilingual.py`;
- `qu/tasks.py` для FR-UND-08 retraining chain.

Fallback:

- если classifier недоступен, использовать embedding только при прохождении
  подписанного threshold;
- при конфликте classifier/embedding не выбирать intent молча;
- возвращать `clarify`, `out_of_scope` или `escalate`;
- откатывать classifier, references и embedding index как совместимый release.

Главные риски: classifier отсутствует, predictions отсутствуют, dataset мал,
hard negatives и RU/EN language switching ограничены.

### LLM profile `sufler_cc`

Contract:

- grounded only in `cc_production`;
- source grounding target 100%;
- answer ≤500 characters;
- p95 ≤2 seconds;
- at least 10 RPS;
- hallucination rate ≤3%.

Evidence:

- `llm_sufler_cc.py`;
- `rag_grounding.py`;
- `llm_load.py`;
- [`llm-profile-matrix.md`](../benchmarks/llm-profile-matrix.md);
- common [`ModelGateway`](../../backend/core/model_gateway.md).

Fallback:

- deterministic approved answer when retrieval reaches the signed threshold;
- otherwise clarification/escalation or operator search;
- never return stub/canned response as production advice;
- no source means no generated answer.

Главные риски: real model absent, manual hallucination rubric absent,
grounding predictions absent, temperature/max_tokens not approved.

### LLM profile `assistant_bank`

Contract:

- contextual chat and source links;
- SSE streaming;
- tool/function-call shape;
- 8k dev context fixture;
- p95 ≤2 seconds and at least 10 RPS;
- tools require policy, RBAC and confirmation.

Evidence:

- `llm_assistant.py`;
- `llm_load.py`;
- [`llm-profile-matrix.md`](../benchmarks/llm-profile-matrix.md);
- common [`ModelGateway`](../../backend/core/model_gateway.md).

Fallback:

- отключить tools/RPA независимо от обычного read-only chat;
- при недоступности модели вернуть явный service unavailable/retry status;
- не выполнять банковскую операцию из текста LLM без policy/confirmation;
- сохранить ручной штатный процесс пользователя.

Главные риски: 8k является dev API fixture, а не vendor tokenizer evidence;
2000 users не тестировались; tool adapters и ИБ policy не реализованы.

### LLM profile `docs_ocr`

Contract:

- OCR text → structured JSON;
- mandatory deterministic validation after LLM;
- on-prem/air-gap;
- invalid/missing fields → HITL, не downstream.

Evidence:

- `llm_docs_ocr.py`;
- [`ocr-llm-pipeline.md`](ocr-llm-pipeline.md);
- [`llm-profile-matrix.md`](../benchmarks/llm-profile-matrix.md);
- common [`ModelGateway`](../../backend/core/model_gateway.md).

Fallback:

- сохранить raw OCR и направить документ в HITL;
- deterministic validator остаётся authority;
- запретить downstream publication без `status=valid`;
- никогда не подменять missing fields вымышленными значениями.

Главные риски: gold field values отсутствуют, strict schema pipeline пока
спецификация, real model и air-gap endpoint не выбраны.

### OCR

Decision:

- Tesseract — reproducible CPU baseline;
- PaddleOCR — первый dev benchmark candidate;
- on-prem IDP — только после vendor/IB due diligence;
- cloud OCR исключён по FR-OCR-22;
- production candidate отсутствует.

Evidence:

- P1-50 [`ocr-candidates.md`](../benchmarks/ocr-candidates.md);
- P1-51
  [`ocr-evaluation-report.md`](../benchmarks/ocr-evaluation-report.md);
- `ocr_extraction.py`;
- P1-53 `llm_docs_ocr.py`;
- [`ocr-llm-pipeline.md`](ocr-llm-pipeline.md).

Fallback:

- обработка через предыдущую подписанную OCR revision;
- при low confidence/schema failure направить в HITL;
- Tesseract может оставаться diagnostic baseline, но не автоматическим
  production fallback без прохождения тех же gates;
- запрещён fallback во внешний cloud API.

Главные риски: sample files отсутствуют, gold values отсутствуют, handwriting
и tables не измерены, весь AG-01…22 checklist pending.

### Optional reranker

Decision:

- slot остаётся `null`;
- default `reranker_ab.py` возвращает documented skip;
- `blocking_for_p1_61=false`;
- baseline retrieval сохраняет порядок без cross-encoder.

Evidence:

- `reranker_ab.py`;
- ModelRegistry `reranker` slot;
- FR-UND-06/12 ranking requirements.

Fallback:

- немедленно отключить reranker feature flag;
- использовать baseline retriever scores и signed thresholds;
- reranker failure не должен останавливать retrieval;
- не резервировать GPU/RAM до доказанного A/B gain.

Главные риски: on-prem model отсутствует, latency cost неизвестен, nDCG target
не утверждён. Skip не блокирует P1-61, но также не доказывает качество.

## Consolidated P1 artifact register

| P1 item | Artifact / suite | State in this selection |
| --- | --- | --- |
| P1-11…P1-13 | ASR streaming/hotword/load JSON | Missing; ASR NO-GO |
| P1-15 | `asr-evaluation-report.md` | Exists; production blocked |
| P1-20 | `embedding-candidates.md`, `embedding_recall.py` | Shortlist/stub only |
| P1-21 | `chunk_grid.py` JSON | Missing; dev defaults only |
| P1-22 | `retrieval_thresholds.py` JSON | Missing; dev defaults only |
| P1-24 | `kb_cc_production` ModelRegistry profile | `dev_frozen`, not measured |
| P1-30 | `qu-architecture.md` | Hybrid accepted for dev |
| P1-31/P1-32 | QU synonym/bilingual JSON | Missing |
| P1-34 | `qu_bilingual.py` | Harness exists; predictions missing |
| P1-40 | `ModelGateway` | Stub/OpenAI-compatible abstraction exists |
| P1-50 | `ocr-candidates.md` | Shortlist and air-gap checklist exist |
| P1-51 | OCR candidate JSON / `ocr_extraction.py` | Measured JSON missing |
| P1-53 | `llm_docs_ocr.py` | Stub contract only |
| P1-61 | QU/OCR/ASR reports and this document | Consolidated; NO-GO |
| P1-62 | `llm-profile-matrix.md` | Draft; IB fields pending |
| Optional | `reranker_ab.py` | Documented non-blocking skip |

## Cross-cutting risks

Open contractual decisions that block production model/transport sign-off are tracked for **humans** in [`docs/development/vii5-decisions-tracker.md`](../development/vii5-decisions-tracker.md) (VII.5 **D1** MRCP vs WS, **D2** СУЗ, **D3** KUMA, **D4** Assistant tools; plus **MS-LLM** vendor gate). Do not auto-close those rows from benchmark scripts.

| Risk | Slots | Impact | Required action |
| --- | --- | --- | --- |
| No measured JSON | All | Production choice cannot be audited | Run suites on versioned datasets and target VM |
| Synthetic/placeholder datasets | ASR, embedding, QU, OCR, LLM | Inflated or meaningless quality | Add anonymized production-like gold data |
| Model revisions/checksums missing | Most slots | Results not reproducible | Pin revision, digest, license and SBOM |
| GPU/RAM unknown | All production services | Capacity/OOM risk | Run sustained load and record peaks |
| Air-gap evidence missing | ASR/LLM/OCR/embedding/QU | IB non-compliance | Verify no egress and offline artifacts |
| Thresholds not measured | Embedding/QU/RAG | Wrong answer or excessive fallback | Calibrate and sign off |
| Hallucination rubric missing | LLM profiles | Unsafe generated answers | Versioned manual/automated grounded rubric |
| Shared endpoint workload unknown | LLM profiles | Cross-profile starvation | Test mixed workload and quotas |
| Rollback compatibility not proven | All | Failed model update can break runtime | Package model/config/index as compatible release |
| Secrets/PII in logs | LLM/OCR/ASR | Security incident | Redaction tests and SIEM audit |
| VII.5 D1 transport unresolved | ASR, telephony | FR-ASR-04 e2e not proven | Human close D1 in vii5-decisions-tracker |
| LLM vendor / MS-LLM unresolved | LLM profiles | Cannot set `prod_candidate` | Human SIGNOFF + tracker MS-LLM row |

## Global fallback policy

1. Fallback must use a previously signed, immutable model/config/index bundle.
2. Automatic fallback to cloud/vendor Internet API is prohibited.
3. A model timeout/error must not be converted into a successful empty answer.
4. Missing retrieval source prohibits ungrounded generation.
5. Low-confidence OCR/QU routes to HITL/clarification/escalation.
6. Tool/RPA execution is disabled independently from read-only assistant chat.
7. Optional reranker failure falls back to baseline retrieval.
8. Every fallback emits a reason code, correlation ID and audit event.
9. Rollback restores compatible model, tokenizer, prompt, thresholds and index.
10. Stub models and placeholder reports are never production fallbacks.

## Gates for production sign-off

Every selected slot must have:

- exact model/revision/digest and runtime;
- approved license, model card, SBOM and vulnerability report;
- versioned representative dataset and immutable predictions/results;
- measured quality against explicit acceptance threshold;
- p50/p95/p99, throughput, sustained duration and zero unexplained failures;
- CPU/RAM/GPU/VRAM peaks on target VM;
- on-prem/air-gap evidence and no-egress test;
- data protection, RBAC, audit and redaction evidence;
- rollback and offline update rehearsal;
- named owner and monitoring/runbook;
- signed change ticket linking all artifacts.

Profile-specific gates from ASR/QU/OCR reports remain mandatory in addition to
this common list.

## SIGNOFF — human reviewer gate

Этот раздел заполняется человеком. Агент, CI или benchmark script не должен
автоматически ставить отметки, имя, решение или дату.

Human reviewer перед P7/P10 production deployment обязан проверить:

- [ ] Для каждого production slot указаны точные model/revision/digest.
- [ ] Все выбранные `prod_candidate` подтверждены measured, не stub JSON.
- [ ] Quality thresholds и datasets утверждены Заказчиком.
- [ ] GPU/RAM/capacity измерены на target test/prod VM.
- [ ] Sustained load завершён без unexplained timeout/OOM/errors.
- [ ] Лицензии, model cards, SBOM и vulnerability reports согласованы.
- [ ] Air-gap/no-egress evidence проверено ИБ.
- [ ] ПДн, secrets, logs, RBAC и audit прошли security review.
- [ ] Fallback/rollback и offline update фактически отрепетированы.
- [ ] Model, tokenizer, prompt, thresholds и index совместимы как release.
- [ ] Acceptance suites и регрессия прошли на release candidate.
- [ ] Change ticket содержит hashes всех reports и artifacts.
- [ ] В ModelRegistry отсутствуют stub-модели в production routing.
- [ ] Для каждого изменяемого слота есть отдельное человеческое решение.

Пустая строка ниже является обязательным production gate. Она остаётся
пустой, пока уполномоченный reviewer лично не примет решение:

| Human reviewer | Role | Decision | Evidence / ticket | Date | Signature |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

Допустимое production-решение: `APPROVED_PROD` или `REJECTED`. Значения
`approved_dev`, `pending`, имя агента или автоматически сформированная подпись
не открывают gate.

### Per-scope review status

| Scope | Decision | Status | Approver | Evidence / ticket | Date |
| --- | --- | --- | --- | --- | --- |
| ASR model | Dev baseline `approved_dev`; no production candidate | `pending` | TBD | Measured P1-11…13 missing | TBD |
| Embedding + KB profile | Dev baseline `approved_dev` only | `pending` | TBD | P1-21/P1-22 missing | TBD |
| QU architecture/model | Hybrid dev architecture only | `pending` | TBD | P1-31/P1-32 missing | TBD |
| LLM `sufler_cc` | Dev stub `approved_dev`; production forbidden | `pending` | TBD | Grounding/load/rubric missing | TBD |
| LLM `assistant_bank` | Dev stub `approved_dev`; production forbidden | `pending` | TBD | Model/load/security missing | TBD |
| LLM `docs_ocr` | Dev stub `approved_dev`; production forbidden | `pending` | TBD | Gold JSON/model missing | TBD |
| OCR model | No production candidate | `pending` | TBD | P1-51/AG evidence missing | TBD |
| Optional reranker | Skipped, non-blocking | `pending` | TBD | Model not configured | TBD |
| GPU/RAM capacity | Not sized | `pending` | TBD | Target VM reports missing | TBD |
| Information security | NO-GO | `pending` | TBD | Air-gap/SBOM/license pending | TBD |
| Customer acceptance | NO-GO | `pending` | TBD | Production evidence missing | TBD |
| P1-61 final decision | Keep all production candidates `null` | `pending` | TBD | This draft | TBD |

## ModelRegistry update policy

This document authorizes `approved_dev` only for the five slots with an
existing `dev_model`. It does not authorize changing any `prod_candidate`,
promoting a slot to production, or changing QU/OCR/reranker from
`evaluating`.

After measured evidence and sign-off:

1. attach exact report paths and hashes to the decision ticket;
2. update this document with measured values and chosen hardware;
3. update ModelRegistry in a reviewed change;
4. validate loader consistency and run regression suites;
5. deploy to test using immutable artifacts;
6. promote only after acceptance and IB approval.

Until then, the valid consolidated decision is:

```text
production candidates: none
capacity sizing: pending
sign-off: pending
fallback: signed dev/previous release or safe degraded mode
```
