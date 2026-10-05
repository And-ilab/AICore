# Протокол приёмки программного обеспечения

**Проект:** AI Hub / Суфлёр — ПО на базе ИИ для банковских процессов  
**Договор:** № 14-03/2026  
**Заказчик:** ОАО «АСБ Беларусбанк»  
**Исполнитель:** ООО «ГС Ритейл»  
**Дата формирования:** 2026-07-27  
**Стенд:** тест / приёмочный стенд AI Hub  
**Источник результатов:** `matrix.json` (наборы SUF-T / CHAT-T / ASS-T / DOC-T / INT-T, VII.2)  

Документ является формальным приложением к приёмке по критериям ТЗ (идентификаторы `*-T-*`). Статусы переносятся из матрицы приёмки без изменения смысла.

## 1. Сводка результатов (pass / fail)

| Статус | Кол-во | Доля |
|---|---:|---:|
| pass (пройден) | 0 | 0.0% |
| fail (не пройден) | 0 | 0.0% |
| pending (не выполнен) | 116 | 100.0% |
| skip (пропущен) | 0 | 0.0% |
| **Всего** | **116** | **100%** |

**Итог:** `in_progress` — **Приёмка не завершена (есть pending)**

## 2. Сводка по модулям

| Модуль | pass | fail | pending | skip | всего |
|---|---:|---:|---:|---:|---:|
| ИИ-ассистент | 0 | 0 | 35 | 0 | 35 |
| Онлайн-чат | 0 | 0 | 20 | 0 | 20 |
| Распознавание документов | 0 | 0 | 17 | 0 | 17 |
| Интеграции | 0 | 0 | 29 | 0 | 29 |
| Суфлёр (телефония / подсказки) | 0 | 0 | 15 | 0 | 15 |

## 3. Результаты по сценариям

### ИИ-ассистент

| id | status |
|---|---|
| ASS-T-01 | pending |
| ASS-T-02 | pending |
| ASS-T-03 | pending |
| ASS-T-04 | pending |
| ASS-T-04a | pending |
| ASS-T-05 | pending |
| ASS-T-06 | pending |
| ASS-T-07 | pending |
| ASS-T-08 | pending |
| ASS-T-09 | pending |
| ASS-T-10 | pending |
| ASS-T-11 | pending |
| ASS-T-12 | pending |
| ASS-T-13 | pending |
| ASS-T-14 | pending |
| ASS-T-15 | pending |
| ASS-T-16 | pending |
| ASS-T-16a | pending |
| ASS-T-17 | pending |
| ASS-T-18 | pending |
| ASS-T-20 | pending |
| ASS-T-21 | pending |
| ASS-T-22 | pending |
| ASS-T-23 | pending |
| ASS-T-LLM-01 | pending |
| ASS-T-MDL-01 | pending |
| ASS-T-PRM-01 | pending |
| ASS-T-QU-01 | pending |
| ASS-T-QU-02 | pending |
| ASS-T-RPT-01 | pending |
| ASS-T-RPT-02 | pending |
| ASS-T-UI-01 | pending |
| ASS-T-UI-02 | pending |
| ASS-T-UI-03 | pending |
| ASS-T-UI-04 | pending |

### Онлайн-чат

| id | status |
|---|---|
| CHAT-T-01 | pending |
| CHAT-T-02 | pending |
| CHAT-T-03 | pending |
| CHAT-T-04 | pending |
| CHAT-T-05 | pending |
| CHAT-T-06 | pending |
| CHAT-T-07 | pending |
| CHAT-T-08 | pending |
| CHAT-T-09 | pending |
| CHAT-T-10 | pending |
| CHAT-T-11 | pending |
| CHAT-T-12 | pending |
| CHAT-T-13 | pending |
| CHAT-T-14 | pending |
| CHAT-T-15 | pending |
| CHAT-T-16 | pending |
| CHAT-T-17 | pending |
| CHAT-T-18 | pending |
| CHAT-T-19 | pending |
| CHAT-T-20 | pending |

### Распознавание документов

| id | status |
|---|---|
| DOC-T-01 | pending |
| DOC-T-02 | pending |
| DOC-T-03 | pending |
| DOC-T-04 | pending |
| DOC-T-05 | pending |
| DOC-T-06 | pending |
| DOC-T-07 | pending |
| DOC-T-08 | pending |
| DOC-T-09 | pending |
| DOC-T-10 | pending |
| DOC-T-11 | pending |
| DOC-T-12 | pending |
| DOC-T-13 | pending |
| DOC-T-14 | pending |
| DOC-T-15 | pending |
| DOC-T-RPT | pending |
| DOC-T-RPT-02 | pending |

### Интеграции

| id | status |
|---|---|
| INT-T-ASR | pending |
| INT-T-ASR-01 | pending |
| INT-T-ASR-02 | pending |
| INT-T-ASR-03 | pending |
| INT-T-AUD | pending |
| INT-T-AUD-01 | pending |
| INT-T-AUD-02 | pending |
| INT-T-AUD-03 | pending |
| INT-T-AUD-04 | pending |
| INT-T-OKT | pending |
| INT-T-OKT-01 | pending |
| INT-T-OKT-02 | pending |
| INT-T-OKT-03 | pending |
| INT-T-OKT-04 | pending |
| INT-T-OKT-05 | pending |
| INT-T-OKT-06 | pending |
| INT-T-OKT-07 | pending |
| INT-T-OKTELL-MRCP | pending |
| INT-T-OKTELL-MRCP-01 | pending |
| INT-T-OKTELL-MRCP-02 | pending |
| INT-T-SUZ | pending |
| INT-T-SUZ-01 | pending |
| INT-T-SUZ-02 | pending |
| INT-T-SUZ-03 | pending |
| INT-T-SUZ-04 | pending |
| INT-T-SUZ-05 | pending |
| INT-T-SUZ-06 | pending |
| INT-T-SUZ-07 | pending |
| INT-T-SUZ-08 | pending |

### Суфлёр (телефония / подсказки)

| id | status |
|---|---|
| SUF-T-01 | pending |
| SUF-T-02 | pending |
| SUF-T-03 | pending |
| SUF-T-04 | pending |
| SUF-T-05 | pending |
| SUF-T-06 | pending |
| SUF-T-07 | pending |
| SUF-T-08 | pending |
| SUF-T-09 | pending |
| SUF-T-10 | pending |
| SUF-T-11 | pending |
| SUF-T-12 | pending |
| SUF-T-13 | pending |
| SUF-T-14 | pending |
| SUF-T-15 | pending |

## 4. Заключение

По состоянию на **2026-07-27** по матрице приёмки (`matrix.json`): **pass=0**, **fail=0**, **pending=116**, **skip=0** (всего 116).

**Решение комиссии (черновик):** Приёмка не завершена (есть pending).

Замечания / особые мнения сторон:

> _Заполнить при подписании._

________________________________________________________________

________________________________________________________________

## 5. Подписи сторон

### 5.1. Заказчик — ОАО «АСБ Беларусбанк»

| Роль | ФИО | Должность | Подпись | Дата |
|---|---|---|---|---|
| Представитель заказчика | ________________ | ________________ | ________________ | __________ |
| Член комиссии | ________________ | ________________ | ________________ | __________ |

### 5.2. Исполнитель — ООО «ГС Ритейл»

| Роль | ФИО | Должность | Подпись | Дата |
|---|---|---|---|---|
| Представитель исполнителя | ________________ | ________________ | ________________ | __________ |
| Член комиссии | ________________ | ________________ | ________________ | __________ |

---

_Шаблон сформирован скриптом `tests/acceptance/generate_protocol.py`. Перегенерируйте после прогона acceptance (обновления `matrix.json`)._
