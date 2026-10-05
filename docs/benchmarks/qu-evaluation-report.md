# Query Understanding evaluation report

Статус: **архитектура рекомендована; quality sign-off заблокирован**  
Дата формирования: 2026-07-20  
Назначение: input для P1-61 `model-selection-v1`

## Executive summary

ADR
[`qu-architecture.md`](../technical/qu-architecture.md)
принимает hybrid-подход:

```text
query → embedding + classifier → fusion → intent → cc_production
```

Рекомендация отчёта:

- утвердить **hybrid QU** как dev-архитектуру;
- сохранить embedding fallback для intent с одной эталонной формулировкой;
- не выбирать QU classifier/model как production candidate;
- не подписывать метрики FR-UND-04/05/06 до появления measured JSON;
- сохранить `qu.prod_candidate: null` и `qu.status: evaluating`.

В `reports/` и `benchmarks/results/` отсутствуют результаты QU suite. Поэтому
ни один процент качества в этом документе не является измеренным.

## Входные артефакты

| Этап | Артефакт | Ожидаемый результат | Состояние |
| --- | --- | --- | --- |
| P1-30 | `docs/technical/qu-architecture.md` | ADR: embedding-only vs classifier vs hybrid | Есть; accepted for dev baseline |
| P1-31 | `qu_synonyms.py` → `reports/qu-synonyms-*.json` | Синонимы, антонимы, порядок слов | JSON отсутствует |
| P1-32 | `qu_bilingual.py` → `reports/qu-bilingual-*.json` | RU/EN same-intent match rate | JSON отсутствует |

Stub-отчёт с `runner_status=stub`, `status=placeholder` или значениями
`null` подтверждает только работоспособность harness и не считается quality
evidence.

## Evaluation datasets

| Dataset | Объём | Покрытие | Статус данных |
| --- | --- | --- | --- |
| `qu-cc-semantic-pairs` | 20 пар | 10 synonyms, 5 antonyms, 5 word-order | Эталонные пары готовы; predictions отсутствуют |
| `qu-cc-bilingual-pairs` | 10 RU/EN пар | CC-SCR-001…010, same intent | Эталонные пары готовы; predictions отсутствуют |
| `cc-reference-scenarios` | 10 сценариев | Договорные CC-SCR | Готовы как источник intent |

Данные синтетические и предназначены для dev-регрессии. Sign-off должен
дополнительно использовать обезличенные реальные формулировки операторов и
клиентов.

## Метрики P1-31

| Категория | Всего cases | Критерий | Latest measured | Статус |
| --- | --- | --- | --- | --- |
| Synonyms / paraphrases | 10 | Match ожидаемого CC-SCR intent | N/A | blocked |
| Antonyms / negation | 5 | Не матчить исходный intent | N/A | blocked |
| Word order | 5 | Сохранять intent при допустимой перестановке и отклонять смену ролей | N/A | blocked |
| Overall pair pass rate | 20 | Все обязательные cases проходят | N/A | blocked |

FR-UND-04 требует работоспособность от одной эталонной формулировки. Поэтому
synonym benchmark должен запускаться и для intent, который ещё не имеет
достаточно данных для classifier retraining: в таком случае решение обязан
обеспечить embedding fallback.

## Метрики P1-32

| Метрика | Cases | Критерий | Latest measured | Статус |
| --- | --- | --- | --- | --- |
| RU intent match rate | 10 | RU-фраза выбирает ожидаемый intent | N/A | blocked |
| EN intent match rate | 10 | EN-фраза выбирает тот же ожидаемый intent | N/A | blocked |
| Cross-language consistency | 10 | RU intent ID = EN intent ID | N/A | blocked |
| Bilingual pair pass rate | 10 | Обе формулировки корректны | N/A | blocked |

SUF-T-12 дополнительно должен проверить переключение языка в одной активной
сессии, а не только независимые RU/EN запросы.

## Recommended architecture

Выбран **hybrid**, поскольку ни один одиночный подход не закрывает требования:

| Подход | FR-UND-04 | FR-UND-06 | Эксплуатационный вывод |
| --- | --- | --- | --- |
| Embedding-only | Сильная сторона: one-shot, synonyms, paraphrases | Может путать близкие intents, отрицание и смену ролей | Использовать как retrieval и mandatory fallback |
| Classifier-only | Требует больше размеченных examples | Даёт контролируемый intent, но не document relevance | Не использовать без embedding |
| Hybrid | One-shot через embedding, known intents через classifier | Fusion обрабатывает конфликт, ambiguity и relevance | **Рекомендован** |

Основные правила:

1. Classifier confidence и document relevance — разные метрики.
2. Intent ограничивает KB scope, но не заменяет retrieval.
3. При согласии classifier/embedding выбирается intent.
4. Новый intent может работать через embedding fallback.
5. При конфликте или top-2 delta ≤5 п.п. выполняется clarification.
6. Ниже `context_inclusion` генерация без источника запрещена.

## Current ModelRegistry state

| Компонент | Текущее значение | Решение |
| --- | --- | --- |
| Embedding dev model | `intfloat/multilingual-e5-large` | Frozen dev baseline, не measured winner |
| KB profile | `kb_cc_production`, status `dev_frozen` | Использовать для P3-03 |
| Context inclusion | `0.60` | Engineering default |
| Deterministic answer | `0.85` | Engineering default |
| QU dev model | `null` | Classifier не выбран |
| QU prod candidate | `null` | Оставить `null` |
| QU status | `evaluating` | Сохранять до measured sign-off |

P1-61 не должен интерпретировать frozen embedding baseline как выбранную
production QU-архитектуру целиком: classifier и fusion ещё не измерены.

## Sign-off recommendation

### Можно подписать сейчас

- архитектурный выбор hybrid;
- контракт `QU → intent → KB`;
- разделение intent confidence и relevance score;
- embedding fallback для one-shot intents;
- маршруты `kb`, `clarify`, `escalate`, `out_of_scope`;
- обязательное логирование model/dataset/profile versions.

### Нельзя подписать сейчас

- pass по FR-UND-04, FR-UND-05 или FR-UND-06;
- конкретную classifier model;
- classifier confidence threshold;
- production recall/precision/F1;
- RU/EN quality;
- production latency/capacity;
- `qu.prod_candidate`.

## Quality gates before model-selection-v1

| Gate | Обязательное доказательство |
| --- | --- |
| One-shot intent | Intent с одной фразой проходит synonym/paraphrase cases через embedding fallback |
| Antonym safety | Все отрицания и смены действия не маршрутизируются в исходный intent |
| Word-order sensitivity | Допустимые перестановки проходят; смена semantic roles отклоняется |
| RU/EN | Обе формулировки выбирают один expected intent |
| Ambiguity | Top-2 delta ≤5 п.п. приводит к clarification |
| Out of scope | Ни classifier, ни retrieval не принуждают KB route ниже порога |
| Relevance contract | Каждый документ имеет нормализованный `relevance_score` |
| Traceability | Лог содержит model, dataset, profile, intent и reason codes |
| Regression | Measured JSON приложены и воспроизводимы по commit/model checksum |

Формальные целевые проценты для QU в ТЗ не заданы. Их необходимо утвердить
до sign-off; до этого отчёт должен публиковать фактические значения без
самостоятельно придуманного договорного порога.

## Open risks

| Риск | Влияние | Следующее действие |
| --- | --- | --- |
| Hybrid P3-03 не реализован | Suite нечего запускать | Реализовать embedding/classifier adapters и fusion |
| Нет classifier model | Нельзя оценить known-intent precision | Составить shortlist и versioned training split |
| Нет measured predictions | Все метрики N/A | Сгенерировать P1-31/P1-32 predictions |
| Dataset мал и синтетический | Риск переоценки качества | Добавить обезличенные production-like RU/EN queries |
| Negation cases ограничены | Возможны unsafe false matches | Расширить hard-negative набор |
| Score calibration отсутствует | Нельзя сравнивать classifier и embedding raw scores | Выполнить отдельную calibration |
| Language switching не измеряется | SUF-T-12 закрыт частично | Добавить multi-turn RU→EN→RU session suite |
| Frozen thresholds не measured | Ошибочные clarify/KB routes | Повторить threshold bench + sign-off |

## Commands to produce missing evidence

P1-31:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\qu_synonyms.py `
  --predictions .\path\qu_predictions.json `
  --output .\reports
```

P1-32:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\qu_bilingual.py `
  --predictions .\path\qu_bilingual_predictions.json `
  --output .\reports
```

После появления measured JSON отчёт необходимо пересобрать: заполнить
таблицы фактическими pass rate, указать model/version/checksum и зафиксировать
решение комиссии sign-off.

## Final decision

**Architecture:** hybrid — recommended and accepted for dev.  
**Quality:** not evaluated.  
**QU model:** not selected.  
**Production candidate:** `null`.  
**P1-61 readiness:** architecture input ready; model-selection evidence
blocked.
