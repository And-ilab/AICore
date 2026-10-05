# Embedding candidates for RAG

Статус: shortlist для calibration, измеренные результаты отсутствуют  
Контекст: FR-LLM-03, FR-LLM-04, FR-LLM-05

## Назначение

Embedding-модель преобразует запрос и фрагменты документов СУЗ в векторы.
Retriever выбирает пять наиболее близких документов, а suite измеряет
`recall@5`: долю запросов, для которых эталонный документ попал в top-5.

FR-LLM-05 требует использовать актуальный индекс и сохранять трассировку
ответа до статьи/фрагмента. FR-LLM-03 и FR-LLM-04 задают калибровку chunk
size, overlap и порогов семантической близости.

## Shortlist

| Кандидат | Назначение в сравнении | Сильные стороны | Что проверить |
| --- | --- | --- | --- |
| `intfloat/multilingual-e5-large` | Основной multilingual baseline | Семейство E5 рассчитано на query/document retrieval и поддерживает несколько языков | Query/passage prefixes, RU/EN recall, CPU/GPU latency, лицензия конкретной версии |
| `BAAI/bge-m3` | Основной альтернативный кандидат | Multilingual retrieval, возможность сравнения dense и расширенных retrieval-режимов | Режим индексирования, размер вектора, память, latency и условия лицензии |
| `Alibaba-NLP/gte-multilingual-base` | Более компактная multilingual альтернатива | Баланс размера и multilingual retrieval | Качество русских перефразировок, длина контекста, совместимость runtime |
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | Контрольный sentence-transformers baseline | Простая локальная интеграция и зрелая экосистема | Recall на банковских запросах, максимальная длина, производительность |

Перед production-использованием для каждой точной revision модели необходимо
зафиксировать model card, commit hash, checksum весов, лицензию, SBOM,
поддерживаемый runtime и происхождение обучающих данных.

## Dataset и метрика

`benchmarks/datasets/embedding_recall.json` содержит 20 синтетических
SUZ-like документов. У каждого документа есть:

- стабильный `SUZ-DOC-*`;
- заголовок и текст статьи;
- синтетический `suz://` source path;
- пользовательский запрос;
- ожидаемый `relevant_document_ids`;
- `top_k=5`.

Синтетический набор проверяет работоспособность harness, но не заменяет
приёмочный набор реальных обезличенных статей СУЗ и запросов операторов.

Формула:

```text
recall@5 = число запросов с эталонным документом в top-5
           / общее число запросов
```

Числовой порог Recall@5 в ТЗ не установлен. Его нельзя объявлять договорным
KPI до утверждения методики и dataset; ModelRegistry поэтому хранит порог
`null`.

## Calibration grid

Первый сравнительный прогон использует одинаковую сетку для всех кандидатов:

- chunk size: 256, 512, 1024 tokens;
- overlap: 50, 100, 200 tokens;
- similarity threshold: 0.60, 0.70, 0.80;
- top-k: 5.

Эти значения являются экспериментальной сеткой, а не утверждёнными
production-настройками. Итоговая конфигурация выбирается по recall, latency,
размеру индекса и доле нерелевантного контекста.

## Запуск stub

```powershell
.\backend\.venv\Scripts\python.exe `
  .\benchmarks\suites\embedding_recall.py `
  --output .\reports
```

Или через единый CLI:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\bench.py run `
  --suite embedding `
  --output .\reports
```

Пока model adapters не подключены, отчёт содержит
`recall_at_5_percent: null` и `status: placeholder` для каждого кандидата.
Такие значения подтверждают только структуру отчёта и не участвуют в выборе
`prod_candidate`.
