# LLM profile matrix — P1-62

Статус документа: **DRAFT — IB sign-off blocked**  
Дата: 2026-07-20  
Назначение: согласование профилей LLM со службой информационной безопасности

## Матрица профилей

| Profile | Model | Temperature | Max tokens | Status |
| --- | --- | --- | --- | --- |
| `sufler_cc` | dev: `stub:sufler_cc`; prod: `null` | `TBD` — отсутствует в ModelRegistry; требуется низкая temperature для строгого суфлёра | `TBD` — отсутствует в ModelRegistry; действует отдельный лимит ответа ≤500 символов | `approved_dev` — только dev/test; не готов к IB prod sign-off |
| `assistant_bank` | dev: `stub:assistant_bank`; prod: `null` | `TBD` — отсутствует в ModelRegistry; ориентир ТЗ 0.3–0.4 | `TBD` — отсутствует в ModelRegistry; ориентир ответа 800–1200 символов, общий текущий лимит ≤500 символов требует решения | `approved_dev` — только dev/test; не готов к IB prod sign-off |
| `docs_ocr` | dev: `stub:docs_ocr`; prod: `null` | `TBD` — отсутствует в ModelRegistry | `TBD` — отсутствует в ModelRegistry; действует отдельный лимит ответа ≤500 символов | `approved_dev` — только dev/test; не готов к IB prod sign-off |

## Source of truth

Машиночитаемый источник конфигурации:
[`backend/config/model_registry.yaml`](../../backend/config/model_registry.yaml).

Соответствие профилей слотам:

- `sufler_cc` → `llm_sufler_cc`;
- `assistant_bank` → `llm_assistant_bank`;
- `docs_ocr` → `llm_docs_ocr`.

Колонки `Model` и `Status` выше отражают текущие `dev_model`,
`prod_candidate` и `status` из ModelRegistry. Значения `temperature` и
`max_tokens` в YAML пока отсутствуют. Значение `response_chars_max` нельзя
автоматически считать `max_tokens`: символы и токены являются разными
единицами.

## Основание в ТЗ

- FR-LLM-01: `temperature` задаётся отдельно для `sufler_cc`,
  `assistant_bank` и `docs_ocr` в пределах, утверждённых ИБ.
- FR-LLM-02: ограничение `max tokens/symbols` задаётся для каждого модуля.
- FR-LLM-05: ответы RAG должны быть трассируемы до статьи или фрагмента.
- FR-LLM-06: контролируется доля галлюцинаций ≤3%.
- FR-LLM-07: SLO платформы — до 500 символов, 1–2 секунды и не менее 10 RPS.
- FR-OCR-22: профиль `docs_ocr` должен работать on-prem в изолированной сети.

Для `assistant_bank` в ТЗ приведён ориентир `temperature=0.3–0.4` и длина
ответа 800–1200 символов. Это ещё не утверждённые значения ModelRegistry.
Для `sufler_cc` указан preset с низкой temperature без числового значения.

## Блокеры P1-62

До sign-off необходимо:

1. выбрать production model для каждого профиля;
2. утвердить числовой `temperature` для каждого профиля;
3. утвердить `max_tokens` и согласовать его с лимитами в символах;
4. определить допустимые границы изменения параметров в admin UI;
5. подтвердить on-prem endpoint, отсутствие запрещённого egress и правила
   журналирования запросов;
6. приложить measured JSON из профильных benchmark suite;
7. после согласования записать значения в ModelRegistry и изменить статус
   только через отдельный review.

## Решение ИБ

| Поле | Значение |
| --- | --- |
| Решение | `pending` |
| Согласующий | `TBD` |
| Дата | `TBD` |
| Номер заявки / протокола | `TBD` |
| Ограничения | `TBD` |

Статус `approved_prod` недопустим, пока хотя бы у одного профиля остаются
`prod_candidate=null`, `temperature=TBD` или `max_tokens=TBD`.
