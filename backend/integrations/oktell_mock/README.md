# Oktell WebSocket mock

Локальный mock имитирует серверный обмен Oktell с будущим адаптером
SuflerTelephony. Он нужен для разработки P4-02 без доступа к реальной АТС.

Источник контракта:
[`tz-oktell-sufler-telephony.md`](../../../docs/integration/oktell-sufler-telephony/tz-oktell-sufler-telephony.md),
раздел VI.2 / INT-T01…INT-T06.

## Запуск

Из корня репозитория:

```powershell
.\backend\.venv\Scripts\python.exe `
  .\backend\integrations\oktell_mock\server.py
```

По умолчанию сервер доступен на:

```text
ws://127.0.0.1:8766
```

Другой порт и задержка между событиями:

```powershell
.\backend\.venv\Scripts\python.exe `
  .\backend\integrations\oktell_mock\server.py `
  --port 9876 `
  --event-delay-ms 100
```

Остановка — `Ctrl+C`.

## Формат Oktell

Сообщение Oktell — JSON-массив из двух элементов:

```json
[
  "command_or_event",
  {
    "qid": "UUID",
    "other": "fields"
  }
]
```

После подключения клиент подписывается на события:

```json
[
  "subscribeevent",
  {
    "qid": "DDA55585-F598-4F8C-B605-E6E186E6D859",
    "event": "phoneevent"
  }
]
```

Mock подтверждает подписку:

```json
[
  "subscribeeventresult",
  {
    "qid": "DDA55585-F598-4F8C-B605-E6E186E6D859",
    "result": 1
  }
]
```

Затем отправляется один детерминированный жизненный цикл:

1. `phoneevent_ringstarted` — звонок поступил на линию, INT-T01;
2. `phoneevent_commstarted` — оператор ответил, INT-T02;
3. `phoneevent_commstopped` — разговор завершён, INT-T03.

Основные поля соответствуют ТЗ:

- `chainid` — ID всей цепочки звонка;
- `commutationid` — ID соединения оператор ↔ клиент;
- `userlogin`, `userid` — оператор Oktell;
- `callerid`, `callername`, `isextline` — внешний абонент;
- `qid` — correlation ID сообщения.

## Dual-leg в mock

Согласно ТЗ, реальные `phoneevent_*` описывают жизненный цикл звонка, а
аудио поступает отдельными leg-файлами/потоками. Поэтому mock не придумывает
новое штатное событие с аудиобайтом. Вместо этого
`phoneevent_commstarted` содержит dev-расширение `mock_audio_legs`:

```json
{
  "mock_audio_legs": [
    {
      "leg": "operator_leg",
      "speaker": "operator",
      "audio_path": "benchmarks/datasets/assets/asr/OKTELL-MOCK-operator.wav",
      "codec": "PCM_S16LE",
      "sample_rate_hz": 8000,
      "status": "placeholder"
    },
    {
      "leg": "client_leg",
      "speaker": "client",
      "audio_path": "benchmarks/datasets/assets/asr/OKTELL-MOCK-client.wav",
      "codec": "PCM_S16LE",
      "sample_rate_hz": 8000,
      "status": "placeholder"
    }
  ]
}
```

`mock_audio_legs` и `mock_recordlinks` являются только расширениями dev-mock
и не должны считаться подтверждёнными полями production API Oktell.
WAV-файлы пока placeholders; адаптер может использовать метаданные для
проверки маршрутизации `operator_leg → operator` и
`client_leg → client`.

## Поддерживаемые команды

- `subscribeevent` с `event=phoneevent` — подтверждение и запуск lifecycle;
- `getchaincontent` — mock-контекст цепочки и коммутации;
- неизвестная команда — сообщение `error` с
  `code=unsupported_command`;
- невалидный JSON или форма сообщения — `invalid_json` /
  `invalid_message_shape`.

WebSocket ping/pong обслуживается библиотекой `websockets`; сервер использует
интервал и таймаут 20 секунд для dev-проверки INT-T11.

## Integration test

```powershell
.\backend\.venv\Scripts\python.exe -m pytest `
  .\tests\integration\test_oktell_mock.py -v
```

Тест поднимает сервер на свободном локальном порту, подключается реальным
WebSocket-клиентом, подписывается и проверяет получение
`phoneevent_ringstarted` и dual-leg данных в `phoneevent_commstarted`.

Mock не реализует ASR, RAG, HTTP `downloadrecordbylink`, авторизацию, TLS или
reconciliation. Это зона следующих адаптеров и интеграционных тестов.
