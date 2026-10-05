# Каталог benchmark-датасетов

Каталог содержит машиночитаемые входные данные для suite из
`benchmarks/suites/`. Точка входа — `manifest.json`: по нему suite находит
набор, проверяет покрываемый модуль и получает repo-relative path к JSON.

## Состав

- `cc_scenarios.json` — 10 эталонных `CC-SCR-*`, перенесённых из договорного
  `docs/sources/technical-requirements/app2-scenarios/manifest.yaml`. Набор
  покрывает QU и LLM; исходный YAML остаётся source of truth.
- `asr_bank_terms.json` — 50 банковских терминов и допустимых вариантов для
  `FR-ASR-09`.
- `asr_samples.json` — синтетические ASR-реплики и placeholder-пути к WAV.
- `rag_query_pairs.json` — запросы для embedding/QU/LLM с ожидаемым
  `CC-SCR-*`, обязательными понятиями ответа и известными
  `source_chunk_ids` для FR-LLM-05 citation grounding.
- `embedding_recall.json` — 20 синтетических SUZ-like документов и
  эталонных запросов для recall@5 и калибровки chunk/threshold.
- `qu_synonyms.json` — 20 CC-SCR-derived пар: синонимы, антонимы и
  проверки чувствительности к порядку слов для FR-UND-04/06.
- `qu_bilingual.json` — 10 пар RU/EN, которые должны разрешаться в один
  CC-SCR intent для FR-UND-05 и SUF-T-12.
- `ocr_samples.json` — placeholder-пути к синтетическим изображениям/PDF,
  синтетический `input.ocr_text` и перечни ожидаемых полей для post-OCR LLM.

Файлы из `assets/asr/` и `assets/ocr/` намеренно пока не добавлены. Запись со
статусом `placeholder` описывает будущий sample, но не означает, что бинарный
файл уже существует. Suite должен явно пропустить такой sample либо завершить
запуск понятной ошибкой; молча считать его успешным нельзя.

## Общий формат dataset

Каждый JSON dataset использует одинаковый верхний уровень:

```json
{
  "schema_version": "1.0",
  "id": "unique-dataset-id",
  "version": "1.0",
  "description": "Назначение набора",
  "modules": ["asr"],
  "tasks": ["transcription"],
  "status": "ready",
  "source": {
    "type": "synthetic",
    "path": "repo/relative/source"
  },
  "samples": []
}
```

Обязательные поля:

- `schema_version` — версия структуры JSON, сейчас `1.0`;
- `id` — стабильный уникальный ID dataset в kebab-case;
- `version` — версия содержимого набора;
- `modules` — один или несколько модулей: `asr`, `embedding`, `qu`, `llm`,
  `ocr`;
- `tasks` — виды измерений, для которых предназначены samples;
- `status` — готовность всего набора;
- `source` — происхождение данных и repo-relative path к источнику;
- `samples` — записи со стабильными уникальными ID.

Допустимые статусы:

- `ready` — sample и необходимые входные файлы готовы;
- `placeholder` — метаданные готовы, но бинарный файл или эталон ещё нужно
  создать;
- `mixed` — набор содержит готовые данные и ожидаемые внешние assets.

Поля внутри `input` и `expected` зависят от задачи. Путь всегда указывается от
корня репозитория с `/`, чтобы одинаково работать в Windows и Linux CI. В
синтетических данных нельзя использовать реальные персональные или банковские
данные.

## Как добавить новый sample

1. Выберите существующий dataset или создайте новый JSON с общим верхним
   уровнем.
2. Присвойте sample уникальный стабильный ID с префиксом набора, например
   `ASR-SYN-011`.
3. Заполните `input`, проверяемый `expected` и `status`.
4. Для WAV, PNG, JPG и PDF укажите будущий или существующий путь в
   `benchmarks/datasets/assets/<type>/`.
5. Если asset ещё отсутствует, поставьте `placeholder`. После добавления и
   ручной проверки файла замените статус на `ready`.
6. Обновите `sample_count`, `modules` и при необходимости запись dataset в
   `manifest.json`.
7. Добавьте или обновите unit-тест suite, который использует sample.

При изменении договорного `manifest.yaml` синхронизируйте
`cc_scenarios.json`, сохраняя исходные `CC-SCR-*`, тексты ветвей и acceptance
ID без переименования.

## Проверка каталога

Из корня репозитория:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest `
  .\tests\benchmarks\test_dataset_catalog.py `
  .\tests\benchmarks\test_asr_hotword.py -v
```

Проверка валидирует JSON, соответствие manifest реальным dataset-файлам,
число samples, уникальность ID и покрытие ASR, embedding, QU, LLM и OCR.
