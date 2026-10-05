# Документация Oktell (заказчик / вендор)

Исходная документация Oktell от банка или вендора: API, WebSocket-события, руководства администратора, схемы ПТК КЦ.

> Это **не** наше ТЗ на интеграцию. Рабочий документ Исполнителя — [tz-oktell-sufler-telephony.md](../../integration/oktell-sufler-telephony/tz-oktell-sufler-telephony.md).

## Файлы в каталоге

| Файл | Назначение |
|------|------------|
| [Вопросы встреча ООО ГС Ритейл.docx](Вопросы%20встреча%20ООО%20ГС%20Ритейл.docx) | As-Is: ответы КЦ/ДИТ по API, ASR, событиям |
| [Руководство_Администратора_2026.pdf](Руководство_Администратора_2026.pdf) | WebSocket, HTTP :4055, MRCP, dual-leg запись |
| [Описание функциональных возможностей системы_2026.pdf](Описание%20функциональных%20возможностей%20системы_2026.pdf) | ПТК КЦ: возможности интеграции, REST, MRCP |

## Ожидаемые дополнительно (запрос к ДИТ / вендору)

См. также блок «Запросить у ДИТ» в [TZ-unified-v1.8%20(МИХ).docx § II.3.4](../../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx) (FR-SUF-04).

- **Руководство по интеграции** Oktell (полное): `phoneevent_*`, `subscribeevent`, JSON-схемы сообщений
- Подтверждение конфигурации **dual-leg** записи и способ доставки leg-аудио в контур суфлёра (real-time vs post-call)
- Направление Web-интеграции (Oktell→CRM / CRM→Oktell), URL, сервисная УЗ Web-API
- Архитектурная схема / информационный обмен ПТК КЦ (при наличии)
- Контакты администратора Oktell и участник техсессии по [VII.5](../../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx) №1–2

## Связанные документы проекта

| Документ | Путь |
|----------|------|
| ТЗ интеграции Oktell ↔ суфлёр | [tz-oktell-sufler-telephony.md](../../integration/oktell-sufler-telephony/tz-oktell-sufler-telephony.md) |
| Техническая спецификация (команда) | [протокол-интеграция-oktell-sufler-telephony.md](../../integration/oktell-sufler-telephony/протокол-интеграция-oktell-sufler-telephony.md) |
| UI вкладка «Суфлёр» | [ai-hub-panel-mockup.md](../../ui/ai-hub-panel-mockup.md) |
