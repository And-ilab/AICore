# SIEM заказчика — Kaspersky KUMA

Централизованный сбор событий ИБ банка — **Kaspersky Unified Monitoring and Analysis Platform (KUMA)**. Требование договора — [prilozhenie-1.md §9.1.9](../technical-requirements/prilozhenie-1.md).

Проектирование интеграции AI Hub выполняется по **открытой документации** Kaspersky (продукт проприетарный; исходники недоступны). Спецификация событий и приёмка — [TZ-unified-v1.8%20(МИХ).docx §VI.3](../../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx).

## Открытые источники (основные)

| Документ | URL |
|----------|-----|
| Administrator's Guide 3.0.3 (PDF) | https://support.kaspersky.com/help/KUMA/3.0.3/en-US/KUMA-3.0.3-en-US.pdf |
| Collector (connectors, normalizers) | https://support.kaspersky.com/kuma/3.0.3/217762 |
| Normalized event data model | https://support.kaspersky.co.uk/kuma/3.0.3/217941 |
| Supported event sources 4.0 | https://support.kaspersky.com/kuma/4.0/255782 |
| REST API v2 — searching events | https://support.kaspersky.com/kuma/3.0.3/269922 |

## Разделение ответственности

| Сторона | Зона |
|---------|------|
| **Исполнитель** | Генерация структурированных событий аудита AI Hub (§9.3 ТТ); локальное хранение ≥1 год; доставка на согласованный endpoint |
| **Заказчик (ДИТ / ИБ)** | Collector KUMA, normalizer, routing → storage/correlator; firewall; версия KUMA; tenant; EPS |

## Ожидается от заказчика (контур банка)

- Версия KUMA (3.x / 4.x) и тестовый tenant
- Endpoint collector: host:port, протокол (TCP / UDP / HTTP)
- Согласованный формат: JSON, CEF или Syslog (+ mapping на normalized model)
- Политика EPS и обязательные поля tenant

## Связанные документы проекта

| Документ | Путь |
|----------|------|
| ТЗ AI Hub v1.2 — VI.3 SIEM / KUMA | [TZ-unified-v1.8%20(МИХ).docx](../../modules/ai-hub/TZ-unified-v1.8%20(МИХ).docx) |
| ТЗ Ассистент — SIEM при нарушении политики | [tz-ai-assistant-belarusbank.md](../../modules/ai-assistant/tz-ai-assistant-belarusbank.md) |
