# Парсер статей belarusbank.by

Скачивает публичные страницы с [belarusbank.by](https://belarusbank.by/) по sitemap и сохраняет UTF-8 `.txt` для локального наполнения БЗ (вместо Битрикс/СУЗ).

## Запуск

```bash
py -3 tools/belarusbank_scraper/scrape_belarusbank.py
```

Полезные флаги:

```bash
# пробный прогон
py -3 tools/belarusbank_scraper/scrape_belarusbank.py --limit 50

# больше параллелизма
py -3 tools/belarusbank_scraper/scrape_belarusbank.py --workers 12

# включить белорусскую версию /be/ и карточки отделений
py -3 tools/belarusbank_scraper/scrape_belarusbank.py --include-be --include-otdeleniya
```

По умолчанию пропуск `/be/` и `/otdeleniya/` (дубликаты языка и адреса отделений). Повторный запуск продолжает с места остановки (`manifest.jsonl`).

## Куда кладёт файлы

```
local/kb/belarusbank/
  articles/
    fizicheskim_licam/   # Физическим лицам
      cards/             # Карты
      credits/           # …
    o-banke/             # О банке
    docs/                # Документы
    business/            # Бизнесу
  manifest.jsonl
  summary.json
  _raw_sitemaps/
```

Каждый файл:

```text
TITLE: …
URL: …
TOPIC: Физическим лицам / Карты
============================================================

текст статьи
```

Далее: загрузить `.txt` в Центр настроек → «Базы знаний КЦ» (drag-and-drop).
