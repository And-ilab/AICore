# OCR candidates — on-prem shortlist

Статус: **shortlist ready; model selection pending P1-51 benchmark**  
Область: Part IV, FR-OCR-01…25  
Ограничение: только on-prem / air-gap по FR-OCR-22

## Executive summary

В shortlist включены три варианта:

1. **Tesseract OCR** — простой CPU baseline;
2. **PaddleOCR** — основной dev-кандидат для benchmark;
3. **On-prem IDP platform** — класс промышленного коммерческого решения,
   конкретный продукт выбирается после проверки поставщика и ИБ.

Cloud OCR API исключены. Production candidate не выбран до измерений P1-51
на согласованном наборе банковских документов.

## Матрица кандидатов

| Кандидат | On-prem / air-gap | RU/EN | Печатный текст | Рукопись | Layout / таблицы | CPU / GPU | Лицензия | Статус |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Tesseract OCR | Да; модели и бинарники можно разместить локально | Да, при установке соответствующих language packs | Базовый кандидат | Ограниченно; требуется отдельная оценка | Ограниченно без дополнительного layout pipeline | CPU; GPU не требуется | Apache-2.0 | `benchmark_baseline` |
| PaddleOCR | Да; модели должны быть заранее загружены в локальный registry/artifact store | Да; проверить выбранные multilingual models | Основной dev-кандидат | Возможности зависят от модели; требуется benchmark | Поддерживает отдельные компоненты detection/layout/table pipeline | CPU/GPU | Apache-2.0 для проекта; лицензии моделей проверяются отдельно | `dev_candidate` |
| On-prem IDP platform | Только редакция с полностью локальным runtime, лицензированием и обновлениями | Обязательно | Ожидается промышленная поддержка | Требуется подтверждение поставщика | Ожидаются классификация, шаблоны, таблицы, validation/HITL | По спецификации поставщика | Proprietary / TBD | `vendor_due_diligence` |

## Почему cloud OCR исключён

FR-OCR-22 требует локальное развёртывание и работу в изолированной сети.
Поэтому SaaS/API, для которых документ или OCR-текст покидает контур банка,
не допускаются в shortlist. Наличие private endpoint или регионального
хранения само по себе не подтверждает air-gap.

Cloud-компонент допустимо рассматривать только после отдельного изменения
требований и письменного согласования ИБ. Текущий P1-51 benchmark не должен
отправлять документы во внешнюю сеть.

## Покрытие Part IV

- FR-OCR-02: классификация и извлечение структурированных данных;
- FR-OCR-06: PDF, JPG/JPEG, PNG и TIFF;
- FR-OCR-07: определение типа документа;
- FR-OCR-08…10: OCR печатного и рукописного текста;
- FR-OCR-11: многостраничные документы;
- FR-OCR-12: русский и английский языки;
- FR-OCR-13/14: извлечение полей и валидация;
- FR-OCR-18: целевая точность не менее 95% на стандартных сканах;
- FR-OCR-19: не менее одной страницы в секунду на поток;
- FR-OCR-20: расширение на новые типы документов;
- FR-OCR-21/22: ИБ, локальное развёртывание и изолированная сеть.

## План P1-51 benchmark

Все кандидаты должны запускаться на одном обезличенном наборе:

- печатные сканы RU и EN;
- фотографии с поворотом, тенями и перспективными искажениями;
- PDF с текстовым слоем и без него;
- многостраничные документы;
- таблицы и банковские реквизиты;
- рукописные поля;
- ухудшенные копии с шумом и низким разрешением.

Минимальные метрики:

- character/word accuracy;
- точность классификации типа документа;
- required-field extraction accuracy;
- доля документов, отправленных на ручную проверку;
- pages per second и latency p50/p95;
- CPU, RAM, GPU/VRAM;
- ошибки и стабильность пакетной обработки.

`benchmarks/datasets/ocr_samples.json` пока является synthetic placeholder.
Для sign-off необходим обезличенный репрезентативный набор со значениями
эталонных полей, а не только именами полей.

## FR-OCR-22 air-gapped deployment checklist

Правило приёмки: кандидат допускается к P1-51 в банковском контуре, только
если все обязательные пункты имеют статус `verified` и к ним приложены
артефакты проверки. Значения `pending` ниже не означают соответствие.

| ID | Обязательная проверка | Проверяемое действие | Артефакт / доказательство | Критерий PASS | Статус |
| --- | --- | --- | --- | --- | --- |
| AG-01 | Зафиксировать состав поставки | Закрепить версии OCR runtime, контейнеров, Python wheels, системных пакетов, language packs и model weights | Версионированный manifest с именами, версиями, размерами и SHA-256 | Каждый устанавливаемый файл присутствует в manifest; плавающих `latest` нет | `pending` |
| AG-02 | Подготовить offline model weights | На connected staging host заранее скачать RU/EN, detection, recognition, layout/table и иные необходимые веса | Каталог artifacts и SHA-256 manifest | Runtime не пытается загрузить веса при первом старте или inference | `pending` |
| AG-03 | Подготовить offline dependencies | Собрать локальный wheel/package repository и контейнерные images по digest | Wheelhouse/repository index; список image digest | Установка выполняется только из внутренних artifacts без обращения к public registry | `pending` |
| AG-04 | Проверить лицензии | Проверить лицензии runtime, каждого набора весов и транзитивных компонентов | License inventory и заключение legal/ИБ | Все компоненты разрешены для банковского production use | `pending` |
| AG-05 | Сформировать SBOM | Сформировать CycloneDX/SPDX SBOM для images и host packages | Подписанный SBOM | SBOM соответствует фактически установленным digest и версиям | `pending` |
| AG-06 | Проверить уязвимости | Просканировать images, wheels и системные пакеты утверждённым offline scanner | Отчёт сканера и список исключений | Нет незакрытых критических уязвимостей; исключения письменно согласованы | `pending` |
| AG-07 | Контролируемый перенос | Передать artifacts в air-gap через утверждённый носитель/шлюз, проверить malware и hashes до и после переноса | Журнал chain of custody, malware report, результаты SHA-256 | Хеши совпадают; вредоносные объекты не обнаружены | `pending` |
| AG-08 | Запретить egress по умолчанию | На firewall/ACL запретить исходящие соединения из OCR subnet/namespace; разрешить только утверждённые внутренние адреса | Экспорт правил firewall/ACL и change ticket | Default deny действует для IPv4 и IPv6; прямой выход и proxy не разрешены | `pending` |
| AG-09 | Исключить обход через DNS/proxy | Удалить public DNS, `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`; проверить service account и sidecar settings | Снимок env/config, DNS policy и proxy policy | Доступны только утверждённые внутренние DNS/hosts; внешние proxy отсутствуют | `pending` |
| AG-10 | Отключить telemetry/update checks | Отключить analytics, crash reporting, license heartbeat и автоматическую проверку обновлений | Конфигурация runtime и vendor confirmation | Startup/inference не требуют внешнего telemetry или license endpoint | `pending` |
| AG-11 | Проверить установку offline | Развернуть новый узел при физически/логически отключённом egress, очистив caches | Installation log с timestamps и inventory после установки | Чистая установка и запуск завершаются без сетевой загрузки | `pending` |
| AG-12 | Доказать отсутствие egress | Во время startup, RU/EN inference, batch и 24-часового soak собирать firewall counters, DNS logs и packet capture | PCAP/flow logs, DNS logs, firewall deny/allow counters | Нет исходящих соединений или DNS-запросов за пределы allowlist | `pending` |
| AG-13 | Negative network test | Из OCR container/VM проверить public DNS, HTTPS и public registries; отдельно проверить IPv6 | Протокол команд с exit codes и сетевые логи | Все внешние проверки блокируются, внутренние разрешённые сервисы доступны | `pending` |
| AG-14 | Защитить входные документы | Подтвердить TLS/mTLS внутри контура, шифрование volumes/backups и запрет public object storage | TLS/storage configuration и test evidence | Документы и OCR-текст не передаются и не хранятся вне банковского контура | `pending` |
| AG-15 | Ограничить временные файлы | Назначить отдельные encrypted temp/work directories, TTL cleanup и запрет core dumps с данными | Mount/config, cleanup test и dump policy | После завершения/ошибки временные документы удаляются по политике | `pending` |
| AG-16 | Проверить логи | Выполнить OCR на canary-документе с маркерными ПДн и проверить application/system logs | Redaction test report | Изображения, полный OCR-текст, реквизиты и ПДн не попадают в открытые логи | `pending` |
| AG-17 | Настроить RBAC и service account | Запускать OCR без root/admin, с read-only runtime и минимальными правами к storage/queue | IAM/RBAC export и container security context | Least privilege подтверждён; чужие документы недоступны | `pending` |
| AG-18 | Проверить аудит | Зафиксировать upload, processing, correction, export, error и admin changes | Пример audit events и проверка доставки в SIEM | События имеют actor, timestamp, document/job ID, action и result без раскрытия ПДн | `pending` |
| AG-19 | Описать offline update | Повторить ingest новой версии через staging → scan → sign → transfer → verify → deploy | Runbook и rehearsal report | Обновление не открывает egress и поддерживает rollback на предыдущие digest/weights | `pending` |
| AG-20 | Проверить backup/restore | Выполнить offline backup и restore конфигурации, шаблонов и разрешённых моделей | Restore protocol и контрольные hashes | Восстановленный узел работает без Internet и с теми же утверждёнными artifacts | `pending` |
| AG-21 | Провести P1-51 | Запустить единый OCR dataset на целевой test VM | JSON benchmark и hardware manifest | Кандидат измерен по FR-OCR-18/19; placeholder не принимается | `pending` |
| AG-22 | Зафиксировать sign-off | ИБ, владелец системы и эксплуатация подписывают результаты AG-01…21 | Протокол/заявка с версиями и hashes | Решение относится к конкретной неизменяемой версии поставки | `pending` |

### Практические проверки no-egress

Команды ниже являются примерами для Linux/Docker-стенда; фактические команды
и средства сбора доказательств утверждает ИБ:

```bash
docker image inspect <image>@sha256:<digest>
sha256sum -c artifacts.sha256
docker run --rm --network none <image>@sha256:<digest> <offline-smoke>
env | rg -i 'http_proxy|https_proxy|all_proxy|no_proxy'
ip route
ip -6 route
```

`--network none` доказывает способность отдельного smoke-run работать без
сети, но не заменяет проверку production network policy. Для итогового
доказательства обязательны firewall/flow/DNS logs при работе в реальном
namespace/subnet.

Negative test должен подтвердить блокировку как минимум:

- public DNS name;
- прямого IPv4 и IPv6 адреса;
- HTTPS endpoint;
- public package/container registry;
- telemetry и license endpoint поставщика.

При этом отдельно проверяется доступность только утверждённых внутренних
PostgreSQL, object storage, queue, registry и SIEM endpoint. Список адресов,
портов и владельцев оформляется как allowlist-приложение к sign-off.

### Матрица статусов кандидатов

| Проверка | Tesseract | PaddleOCR | On-prem IDP |
| --- | --- | --- | --- |
| Offline install smoke AG-01…11 | `pending` | `pending` | `pending` |
| No-egress evidence AG-12…13 | `pending` | `pending` | `pending` |
| Data protection AG-14…18 | `pending` | `pending` | `pending` |
| Update/restore AG-19…20 | `pending` | `pending` | `pending` |
| P1-51 and sign-off AG-21…22 | `pending` | `pending` | `pending` |

## Предварительная рекомендация

- использовать **Tesseract** как воспроизводимый CPU baseline;
- первым измерить **PaddleOCR** как dev-кандидат;
- допустить **on-prem IDP** к сравнению только после заполнения vendor
  questionnaire, проверки лицензирования и демонстрации в air-gap;
- не записывать `ocr.prod_candidate` в ModelRegistry до measured benchmark и
  sign-off ИБ.
