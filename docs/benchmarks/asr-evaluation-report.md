# ASR evaluation report

Статус: **NO-GO для выбора production-модели**  
Дата формирования: 2026-07-20  
Назначение: input для `model-selection-v1` / P1-15

## Executive summary

На момент формирования отчёта в репозитории отсутствуют JSON-результаты
бенчмарков в `reports/` и `benchmarks/results/`. Реализованные suite могут
создавать stub-отчёты, но placeholder-значения не подтверждают KPI.

Итоговое решение:

- `dev_model`: `vosk-model-small-ru-0.22` — оставить для разработки
  интеграции;
- `prod_candidate`: **`null`** — production-кандидат не выбран;
- статус ModelRegistry: **`evaluating`**;
- выпуск `model-selection-v1`: заблокирован до измеренных P1-11…P1-13 JSON;
- Vosk остаётся первым кандидатом для PoC, но не получает production-статус
  без RU/EN, 8 kHz, hotword и нагрузочных результатов.

Назначение Vosk production-кандидатом только на основании работающего dev
прототипа было бы некорректно: публичные модели показывают отличающееся
качество на телефонной речи, а текущие WAV в dataset являются placeholders.

## Входные результаты P1-11…P1-13

| Этап | Suite и ожидаемый JSON | Проверяемые показатели | Latest result | Статус |
| --- | --- | --- | --- | --- |
| P1-11 | `bench run --suite asr` → `reports/asr-*.json` | RU/EN WER, chunk p95, 8 kHz | Файл отсутствует | blocked |
| P1-12 | `asr_hotword.py` → `reports/asr_hotword.json` | term accuracy без/с hotword boost, 50 терминов | Файл отсутствует | blocked |
| P1-13 | `asr_load.py` → `reports/asr-load-*.json` | 70 concurrent streams, p95, failures, hardware | Файл отсутствует | blocked |

Stub JSON, в котором `runner_status=stub`, `status=placeholder`, WER или
accuracy равны `null`, не считается результатом P1-11…P1-13.

## KPI и результаты

| KPI | Целевое значение | FR | Latest measured | Решение |
| --- | --- | --- | --- | --- |
| RU word accuracy / WER | accuracy ≥90% / WER ≤10% | FR-ASR-02, FR-ASR-03 | Нет данных | blocked |
| EN word accuracy / WER | accuracy ≥90% / WER ≤10% | FR-ASR-01, FR-ASR-03 | Нет данных | blocked |
| Streaming latency p95 | ≤1000 ms | FR-ASR-04 | Нет данных | blocked |
| Параллельные звонки | ≥70, failures=0 | FR-ASR-03 | Нет данных | blocked |
| Телефонный канал | 8 kHz PSTN/VoIP | FR-ASR-07 | Нет данных | blocked |
| Банковский словарь | Измеримое улучшение term accuracy | FR-ASR-09 | Нет данных | blocked |
| Автопунктуация | Включена и проверена на эталоне | FR-ASR-08 | Нет данных | blocked |
| RU/EN dual-leg | operator/client обрабатываются независимо | FR-ASR-01, FR-ASR-06 | Только mock metadata | blocked |

Формулировка ТЗ `WER ≥90%` нормализована как **word accuracy ≥90% /
WER ≤10%**, поскольку меньший WER означает меньше ошибок.

## Сравнение кандидатов

Технический shortlist подробно приведён в
[`asr-candidates.md`](asr-candidates.md). Ни один кандидат пока не запускался
на едином банковском наборе.

| Кандидат | Зафиксированная версия для теста | RU WER | EN WER | p95 | Hotword | 70 streams | Текущий вывод |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Vosk | Dev: `vosk-model-small-ru-0.22`; production RU/EN версии не зафиксированы | N/A | N/A | N/A | N/A | N/A | Первый PoC; не production |
| OpenAI Whisper | Не зафиксирована | N/A | N/A | N/A | N/A | N/A | Нужны streaming-обвязка и 8→16 kHz resampling |
| Kaldi | Acoustic/LM recipe не зафиксирован | N/A | N/A | N/A | N/A | N/A | Toolkit; высокая стоимость подготовки |
| NVIDIA Riva / Speech NIM | Container/model/GPU не зафиксированы | N/A | N/A | N/A | N/A | N/A | Vendor PoC после проверки лицензии и GPU |

Yandex SpeechKit исключён из shortlist: в As-Is он является внешней
зависимостью Oktell, тогда как целевой ASR должен работать on-prem в контуре
банка.

## Рекомендация для ModelRegistry

До получения measured JSON сохраняется:

```yaml
asr:
  dev_model: vosk-model-small-ru-0.22
  prod_candidate: null
  status: evaluating
```

Рекомендуемый порядок PoC:

1. Vosk — минимальная стоимость входа, нативный streaming и CPU inference.
2. NVIDIA Riva / Speech NIM — vendor-кандидат для сравнения качества и
   масштабирования на выделенной NVIDIA GPU.
3. Whisper — только с зафиксированной streaming-реализацией и подтверждением
   сквозного p95 после 8→16 kHz.
4. Kaldi — если банк готов поддерживать собственные acoustic/LM recipes.

`prod_candidate` может быть заполнен только моделью, которая одновременно:

- прошла RU и EN WER на одном versioned dataset;
- прошла телефонный набор 8 kHz и шумовые сценарии;
- показала measured p95 ≤1000 ms;
- обработала 70 потоков без ошибок на задокументированном hardware;
- показала улучшение банковских терминов с hotword boost;
- прошла проверку on-prem, лицензии, SBOM и ИБ.

Если ни одна модель не проходит все обязательные критерии, решение остаётся
`null`; выбирать «лучшую из не прошедших» нельзя.

## Открытый риск D1: MRCP vs WebSocket + dual-leg

Источник:
[VII.5.2 D1](../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx)
и вопросы №1–2
[VII.5.3](../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx).
**Human status/owner/deadline:** [`docs/development/vii5-decisions-tracker.md`](../development/vii5-decisions-tracker.md) (do not auto-close).

| Вариант | Преимущества | Риски / неизвестные | Что требуется для закрытия |
| --- | --- | --- | --- |
| MRCP v2 | Стандартный streaming ASR-контур; естественная передача аудио и результатов распознавания | Binding Oktell, codec, NLSML/plain text, порты и реальная поддержка в установленной версии не подтверждены | Техсессия с Oktell, тестовая MRCP-сессия и сквозной p95 |
| Модель T: WebSocket `phoneevent_*` + dual-leg | Соответствует подготовленному VI.2 и dev-mock; надёжный speaker mapping без voiceprint | Не подтверждены доступность leg во время разговора, задержка появления записи, codec и режим incremental; post-call leg не обеспечивает real-time | Тестовая линия, реальные dual-leg 8 kHz, согласованная схема событий и latency test |

Решение D1 влияет не только на adapter P4-02, но и на достоверность ASR
latency. Текущий streaming benchmark измеряет decoder time; P1-15 должен
дополнительно включить transport/buffering/endpointing:

```text
Oktell audio → adapter → ASR partial/final → SuflerTelephony
```

До закрытия D1 нельзя считать p95 локальной обработки доказательством
сквозного FR-ASR-04.

## Остальные открытые риски

| Риск | Влияние | Действие |
| --- | --- | --- |
| Нет реальных RU/EN dual-leg WAV | Невозможно измерить договорный WER | Получить обезличенный versioned набор звонков Oktell |
| ASR dataset содержит placeholder paths | Suite формирует stub | Добавить WAV и изменить sample status на `ready` |
| Нет двух зафиксированных моделей RU/EN | Билингвальность не проверяется | Зафиксировать model name, checksum, license |
| Hotword suite принимает готовые transcripts | Не проверен реальный механизм boost | Сделать два прогона одного ASR/config с boost off/on |
| Load suite без модели проверяет только async harness | 70 реальных recognizer не подтверждены | Запустить `mode=async_vosk` на целевом сервере |
| Hardware/GPU не утверждены | p95 и capacity невоспроизводимы | Зафиксировать CPU/RAM/GPU/driver/container |
| Публичные WAV/модели не отражают банковскую телефонию | Риск ложного выбора | Использовать единый банковский 8 kHz test set |
| Лицензии model weights и training data | Юридический/ИБ риск | License review и SBOM до shortlist decision |

## Команды для получения недостающих JSON

Streaming WER/p95:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\bench.py run `
  --suite asr `
  --output .\reports
```

Hotword:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\asr_hotword.py `
  --without-boost .\path\without_boost.json `
  --with-boost .\path\with_boost.json `
  --output .\reports\asr_hotword.json
```

Load:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\asr_load.py `
  --streams 70 `
  --output .\reports
```

После появления measured JSON этот отчёт необходимо пересобрать: заменить
`N/A`, указать точные версии моделей и hardware, приложить пути к latest
файлам и только затем принять решение `prod_candidate`.
