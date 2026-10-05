# OCR evaluation report

Статус: **NO-GO для выбора production candidate**  
Дата формирования: 2026-07-20  
Назначение: input для P1-61 model selection  
Источники: P1-50 candidate shortlist и ожидаемые P1-51 benchmark JSON

## Executive summary

Технический shortlist P1-50 готов:
[`ocr-candidates.md`](ocr-candidates.md). В него входят Tesseract, PaddleOCR
и класс промышленного on-prem IDP.

На момент формирования отчёта:

- каталог `reports/` отсутствует;
- в `benchmarks/results/` нет OCR JSON;
- `benchmarks/datasets/ocr_samples.json` содержит synthetic OCR text и
  placeholder-пути, но реальные PDF/images отсутствуют;
- dataset задаёт имена ожидаемых полей, но не gold field values;
- FR-OCR-22 checklist AG-01…22 не подтверждён evidence;
- ни один кандидат не измерен на одной target VM.

Решение:

- `ocr.dev_model`: оставить `null` до фиксации точной версии первого PoC;
- первым измерить **PaddleOCR** как dev-кандидат;
- использовать **Tesseract** как CPU baseline;
- `ocr.prod_candidate`: оставить **`null`**;
- `ocr.status`: оставить **`evaluating`**;
- P1-61 sign-off заблокирован до measured P1-51 JSON и air-gap evidence.

Выбор PaddleOCR production-кандидатом только по функциональному shortlist был
бы некорректен: отсутствуют измерения точности, производительности, рукописи,
таблиц, RU/EN и required fields.

## Входные артефакты

| Этап | Артефакт | Ожидаемый результат | Latest state |
| --- | --- | --- | --- |
| P1-50 | `docs/benchmarks/ocr-candidates.md` | On-prem shortlist и FR-OCR-22 checklist | Есть; checklist pending |
| P1-51 | `ocr_extraction.py` → `reports/ocr-extraction-*.json` | Field accuracy по типам документов | JSON отсутствует |
| P1-51 | Candidate OCR engine report | Character/word accuracy, classification, pages/sec, p95 | JSON отсутствует |
| P1-53 | `llm_docs_ocr.py` → `reports/llm-docs-ocr-*.json` | OCR text → `docs_ocr` → structured JSON | JSON отсутствует |
| P6-01/P6-03 | `docs/technical/ocr-llm-pipeline.md` | Целевой pipeline и validation contract | Спецификация есть; реализация pending |

Stub-отчёт с `runner_status=stub`, `status=placeholder` или синтетическими
предсказаниями подтверждает только работу harness. Он не является P1-51
quality evidence.

## KPI и latest metrics

| Метрика | Цель / критерий | Требование | Latest measured | Решение |
| --- | --- | --- | --- | --- |
| OCR accuracy на стандартных сканах | ≥95% | FR-OCR-18, DOC-T-01 | N/A | blocked |
| Производительность | ≥1 page/sec на поток | FR-OCR-19, DOC-T-06 | N/A | blocked |
| Required-field extraction | Все обязательные поля извлечены и валидированы | FR-OCR-13/14, DOC-T-04 | N/A | blocked |
| Document type accuracy | Тип определён; доступна ручная переквалификация | FR-OCR-07, DOC-T-03 | N/A | blocked |
| RU/EN | Оба языка на общем наборе | FR-OCR-12 | N/A | blocked |
| Поддерживаемые форматы | PDF/JPG/JPEG/PNG/TIFF | FR-OCR-06 | Только dataset metadata | blocked |
| Печатный/рукописный текст | Оба вида проверены | FR-OCR-09/10 | N/A | blocked |
| Многостраничные документы | Полный порядок страниц и текст | FR-OCR-11 | N/A | blocked |
| JSON validation | Strict schema, missing fields, anomalies | FR-OCR-14 | Только stub contract | blocked |
| Air-gap | AG-01…22 verified | FR-OCR-22, DOC-T-13 | 0 verified | blocked |

Текущий `ocr_extraction.py` считает non-empty required field names. Без gold
field values этот показатель не подтверждает правильность распознанных сумм,
дат, реквизитов и идентификаторов.

## Сравнение кандидатов

| Кандидат | Зафиксированная версия | Accuracy | Fields | Pages/sec | RU/EN | Handwriting | Air-gap | Вывод |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Tesseract OCR | Не зафиксирована; language packs не зафиксированы | N/A | N/A | N/A | Не измерено | Не измерено | Pending | CPU baseline |
| PaddleOCR | Runtime/models/digests не зафиксированы | N/A | N/A | N/A | Не измерено | Не измерено | Pending | Первый dev benchmark |
| On-prem IDP | Поставщик и редакция не выбраны | N/A | N/A | N/A | Не подтверждено | Не подтверждено | Pending | Vendor due diligence |

Cloud OCR не рассматривается: FR-OCR-22 требует локальную работу в
изолированной сети. Private endpoint без доказанного отсутствия egress не
считается air-gap.

## Рекомендация для ModelRegistry

Текущее безопасное состояние:

```yaml
ocr:
  dev_model: null
  prod_candidate: null
  status: evaluating
```

PaddleOCR получает только приоритет первого PoC. После фиксации версии,
model weights, license и SHA-256 допускается отдельное изменение
`dev_model`, например на идентификатор неизменяемой внутренней сборки.
Это не должно автоматически заполнять `prod_candidate`.

`prod_candidate` можно заполнить только кандидатом, который:

1. запущен на одном versioned gold dataset с остальными кандидатами;
2. достиг OCR accuracy ≥95% на стандартных сканах;
3. достиг ≥1 page/sec на поток на задокументированной target VM;
4. показал field value accuracy по каждому обязательному `document_type`;
5. прошёл PDF/images, RU/EN, multi-page, tables и handwriting subsets;
6. сформировал strict validated JSON без пропуска обязательных полей;
7. прошёл error, batch и stability tests;
8. имеет pinned runtime/model digests, license inventory и SBOM;
9. закрыл AG-01…22 с evidence и sign-off ИБ;
10. имеет rollback и offline update procedure.

Если ни один кандидат не проходит все обязательные gates, значение остаётся
`null`. Выбирать «лучший из не прошедших» запрещено.

## Требуемый P1-51 JSON

Для каждого кандидата нужен отдельный неизменяемый отчёт:

```json
{
  "schema_version": "1.0",
  "candidate": {
    "name": "paddleocr",
    "runtime_version": "pinned",
    "model_digests": ["sha256:..."]
  },
  "dataset": {
    "id": "bank-ocr-gold-v1",
    "version": "1.0",
    "document_count": 0,
    "page_count": 0
  },
  "hardware": {
    "cpu": "TBD",
    "ram_gb": 0,
    "gpu": "TBD"
  },
  "metrics": {
    "ocr_accuracy_percent": null,
    "field_value_accuracy_percent": null,
    "document_type_accuracy_percent": null,
    "pages_per_second": null,
    "latency_p50_ms": null,
    "latency_p95_ms": null,
    "hitl_rate_percent": null,
    "error_rate_percent": null
  },
  "subsets": {
    "ru": null,
    "en": null,
    "printed": null,
    "handwritten": null,
    "tables": null,
    "multi_page": null
  },
  "air_gap": {
    "checklist_version": "AG-01..22",
    "verified": false,
    "evidence_ref": null
  }
}
```

Нулевые и `null` значения в примере являются схемой заполнения, а не
результатами.

## Открытые риски

| Риск | Влияние | Действие |
| --- | --- | --- |
| Нет реальных sample files | Нельзя измерить OCR engine | Добавить обезличенные versioned PDF/images |
| Нет gold field values | Нельзя отличить наличие ключа от правильного значения | Разметить значения и правила normalization |
| Один документ на тип | Метрика нестабильна и нерепрезентативна | Расширить каждый тип по качеству/формату/языку |
| Нет handwriting/table subsets | Не проверены сложные требования Part IV | Добавить отдельные subsets и отчётность |
| Не зафиксированы model weights | Результат невоспроизводим | Сохранить weights offline с SHA-256 |
| IDP-кандидат не определён | Невозможно сравнить коммерческое решение | Получить vendor questionnaire и air-gap demo |
| AG checklist pending | Нет compliance FR-OCR-22 | Выполнить AG-01…22 и приложить evidence |
| Нет target VM | Throughput/p95 нельзя использовать для capacity | Утвердить CPU/RAM/GPU и deployment topology |
| Post-OCR LLM только stub | P6-03 validation не измерена | Настроить real `docs_ocr` и gold JSON |

## Команды для подготовки отчётов

Stub harness:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\bench.py run `
  --suite ocr `
  --output .\reports
```

Оценка готовых результатов OCR-кандидата:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\ocr_extraction.py `
  --predictions .\reports\p1-51-paddleocr-predictions.json `
  --output .\reports
```

Post-OCR LLM:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\llm_docs_ocr.py `
  --mode openai `
  --output .\reports
```

После появления measured JSON этот отчёт необходимо пересобрать:

- указать точные пути к latest artifacts;
- заменить N/A только измеренными значениями;
- сравнить кандидатов на одном dataset и hardware;
- приложить AG evidence;
- зафиксировать решение и sign-off;
- только затем обновить `ocr.prod_candidate` и `ocr.status`.

## Sign-off

| Роль | Решение | Имя / ссылка | Дата |
| --- | --- | --- | --- |
| Владелец OCR | `pending` | TBD | TBD |
| ИБ | `pending` | TBD | TBD |
| Архитектура | `pending` | TBD | TBD |
| Эксплуатация | `pending` | TBD | TBD |
| P1-61 model selection | `blocked` | Нет measured P1-51 | 2026-07-20 |
