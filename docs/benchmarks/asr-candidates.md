# Shortlist ASR-кандидатов для on-prem

Статус: input для P1-11…P1-15 и `model-selection-v1`  
Дата актуализации: 2026-07-20

## Цель и критерии

Shortlist предназначен для выбора движка потокового распознавания телефонии
в контуре банка. Кандидат должен проверяться по
[FR-ASR-01…09](../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx):

- RU/EN и потоковая выдача partial/final — FR-ASR-01;
- устойчивость к шуму и современная лексика — FR-ASR-02, FR-ASR-06;
- точность распознавания не менее 90% при нагрузке от 70 звонков —
  FR-ASR-03;
- p95 распознавания не более 1 секунды — FR-ASR-04;
- пригодность для QA и хранения транскриптов — FR-ASR-05;
- телефонный канал 8 kHz — FR-ASR-07;
- автоматическая пунктуация — FR-ASR-08;
- банковские словари, аббревиатуры и hotword boost — FR-ASR-09.

В ТЗ встречается формулировка `WER ≥90%`, но WER является долей ошибок и
должен уменьшаться. Для сравнения моделей используется эквивалентный
корректный критерий: **word accuracy ≥90% / WER ≤10%**.

## Кандидаты

| Кандидат | On-prem | RU/EN | Streaming | Телефония 8 kHz | Лицензия | GPU |
| --- | --- | --- | --- | --- | --- | --- |
| **Vosk** | Да, полностью offline | Да; отдельные RU и EN модели | Да, нативный streaming API с partial/final | Да, при выборе narrowband/mixed-band модели или согласованном resampling; обязательна проверка на звонках Oktell | API — Apache-2.0; лицензию конкретной модели проверять отдельно, официальные выбранные модели помечены Apache-2.0 | Для inference не обязателен; CUDA возможна для серверной сборки/обучения |
| **OpenAI Whisper** | Да, веса и inference можно разместить локально | Да, multilingual-модели | Не нативно; near-real-time только через chunking/VAD и обвязки вроде WhisperLive/faster-whisper | Вход необходимо преобразовать 8→16 kHz; модель не оптимизирована специально под телефонный канал | Код и веса OpenAI Whisper — MIT; лицензии обвязки проверяются отдельно | Не обязателен для tiny/base, но практически нужен для p95 и 70 одновременных звонков |
| **Kaldi** | Да, полностью локальная сборка | Да, если подготовлены соответствующие акустические и языковые модели; это toolkit, а не готовая единая модель | Да, через online2/online decoding pipeline | Да, при использовании 8 kHz telephony recipe/model | Toolkit — Apache-2.0; модели и обучающие данные имеют собственные лицензии | Не обязателен для базового CPU inference; полезен/необходим для обучения и высоконагруженного GPU pipeline |
| **NVIDIA Riva / Speech NIM** | Да, контейнеры в локальном ЦОД/изолированном контуре | Да, доступны RU и EN ASR-модели; конкретную пару model/version фиксировать перед PoC | Да, официальный streaming API | Да, API принимает от 8 kHz и выполняет resampling; качество конкретной RU/EN модели на PSTN всё равно проверяется стендом | Проприетарные условия NVIDIA; production обычно через NVIDIA AI Enterprise, условия и экспортные ограничения проверяет закупка/ИБ | Да, NVIDIA GPU обязателен; актуальная матрица NIM требует совместимую GPU и достаточный VRAM |

Таблица подтверждает только техническую пригодность к PoC. Она не заменяет
проверку конкретной версии модели, model card, лицензии весов, состава
обучающих данных и совместимости с серверным оборудованием банка.

## Рекомендация для dev — Vosk

Для первого dev-контура рекомендуется **Vosk**:

1. Уже выбран в `backend/config/model_registry.yaml` как
   `vosk-model-small-ru-0.22`.
2. Работает offline и запускается на CPU без обязательной NVIDIA GPU.
3. Имеет простой Python API и нативную потоковую обработку аудиочанков.
4. Поддерживает RU/EN отдельными моделями и перенастраиваемый словарь, что
   позволяет начать проверку FR-ASR-09.
5. Быстро интегрируется с текущим WebSocket dev-сервисом и подходит для
   проверки полного пути «аудио → partial/final → QU».

Это **dev-выбор, а не утверждение production-кандидата**. Публичные результаты
Vosk на русских телефонных звонках существенно зависят от модели и могут не
достичь договорной точности. `vosk-model-small-ru-0.22` должен использоваться
для интеграции, а не автоматически считаться прошедшим FR-ASR-03.

## План сравнения P1-11…P1-15

Для каждого кандидата фиксируется точная версия движка и модели, после чего
на одном наборе dual-leg записей Oktell выполняются:

1. RU и EN accuracy/WER, отдельно для чистого и зашумлённого аудио.
2. Проверка 8 kHz PCM/G.711 без потери качества при преобразовании.
3. p50/p95 partial и final latency, включая 70 параллельных звонков.
4. Тест 50 банковских терминов с hotword boost и без него.
5. Пунктуация, разделение каналов, стабильность длительной сессии.
6. Замеры CPU/GPU/RAM/VRAM и расчёт количества worker/node.
7. Проверка лицензии, SBOM, обновлений, on-prem support и отсутствия
   обязательного исходящего сетевого трафика.

Production-кандидат заполняется в ModelRegistry только после отчёта с
результатами этих прогонов.

## Почему исключён Yandex SpeechKit

Yandex SpeechKit не входит в shortlist. В As-Is документации Oktell он
упоминается как внешний сервис синтеза речи, тогда как целевой поток задаёт
**dual-leg Oktell → on-prem ASR суфлёра**, без Oktell STT/SpeechKit. Облачная
зависимость также противоречит требованию работы контура телефонии без
доступа в Интернет. SpeechKit можно учитывать только как описание As-Is, но
не как production-кандидат настоящего отбора.

## Источники

- [Vosk API](https://alphacephei.com/vosk/) — offline, RU/EN, streaming,
  reconfigurable vocabulary.
- [Vosk models](https://alphacephei.com/vosk/models) — модели, полосность,
  публичные WER и лицензии конкретных моделей.
- [OpenAI Whisper](https://github.com/openai/whisper) — multilingual,
  лицензия MIT, требования моделей.
- [Whisper audio implementation](https://github.com/openai/whisper/blob/main/whisper/audio.py)
  — входной waveform 16 kHz.
- [Kaldi](https://github.com/kaldi-asr/kaldi) — toolkit и online pipelines.
- [NVIDIA Riva ASR](https://docs.nvidia.com/deeplearning/riva/user-guide/docs/asr/asr-overview.html)
  — RU/EN, streaming и GPU pipeline.
- [Riva ASR API](https://docs.nvidia.com/deeplearning/riva/user-guide/docs/reference/protos/riva_asr.proto.html)
  — `sample_rate_hertz`, минимум 8 kHz и server-side resampling.
- [NVIDIA ASR NIM support matrix](https://docs.nvidia.com/nim/speech/latest/reference/support-matrix/asr.html)
  — актуальные модели и аппаратные требования.
- [Единое ТЗ v1.4 — FR-ASR-01…09](../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx).
