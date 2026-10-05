#!/usr/bin/env python3
"""Compile belarusbank.by pages into 4 scenario-topic KB documents.

Usage (from repo root):
  py -3 tools/belarusbank_scraper/compile_scenario_topics.py
"""

from __future__ import annotations

import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from scrape_belarusbank import _fetch, extract_article  # noqa: E402


def _extract_pdf_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return ""
    from io import BytesIO

    reader = PdfReader(BytesIO(raw))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    text = "\n".join(pages)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_page(url: str) -> tuple[str, str, str]:
    """Return (title, text, error)."""
    try:
        raw = _fetch(url)
        if raw[:5] == b"%PDF-":
            text = _extract_pdf_text(raw)
            if len(text) < 200:
                return "", text, f"pdf_short:{len(text)}"
            known = {
                "309885": "ПРАВИЛА ОАО «АСБ Беларусбанк» по отправлению международного банковского перевода физического лица",
                "309887": "Примеры оформления платежного поручения на международный перевод (в т.ч. в RUB в РФ)",
            }
            title = next((name for key, name in known.items() if key in url), "")
            if not title:
                title = next((ln.strip() for ln in text.splitlines() if ln.strip()), url)
            return title[:220], text, ""
        html = raw.decode("utf-8", errors="replace")
        title, text = extract_article(html, url)
        if text.lstrip().startswith("%PDF"):
            return title, "", "pdf_as_html"
        if len(text) < 200:
            return title, text, f"short_text:{len(text)}"
        return title, text, ""
    except HTTPError as exc:
        return "", "", f"http_{exc.code}"
    except (URLError, TimeoutError, OSError) as exc:
        return "", "", f"network:{exc}"[:220]

COLLECTED = date.today().isoformat()
OUT_DIR = Path(__file__).resolve().parents[2] / "local" / "kb" / "scenario-topics"

HEADER_NOTE = (
    "Источник: публичные страницы belarusbank.by. Ставки, комиссии и условия "
    "на сайте меняются — оператор сверяет актуальные цифры по ссылке перед ответом клиенту. "
    "Ниже — текст страниц на дату сбора, без выдуманных условий."
)

TOPICS: list[dict] = [
    {
        "filename": "avtokredit-belarusbank.txt",
        "title": "Автокредит Беларусбанка",
        "urls": [
            "https://belarusbank.by/fizicheskim_licam/kredit/consumer/kredit-na-priobretenie-avtomobilya-elektromobilya-/",
            "https://belarusbank.by/fizicheskim_licam/kredit/consumer/kredit-lyegka-ekhats-na-priobretenie-avtomobilya-elektromobilya-v-ramkakh-zaklyuchennykh-dogovorov-s/",
            "https://belarusbank.by/fizicheskim_licam/kredit/consumer/kredit-na-priobretenie-u-dilerov-szao-beldzhi-avtomobiley-marki-belgee-modeli-s50-x50-x70-x80/",
            "https://belarusbank.by/fizicheskim_licam/kredit/consumer/kredit-na-priobretenie-u-dilerov-szao-beldzhi-elektromobiley-marki-geely-modeli-ex5/",
            "https://belarusbank.by/ru/fizicheskim_licam/kredit/consumer/43559",
            "https://belarusbank.by/o-banke/press/news/chastnym-klientam/teper-i-x80-mozhno-priobresti-v-kredit-s-belarusbankom-menyayutsya-usloviya-po-kreditu-na-pokupku-be/",
            "https://belarusbank.by/o-banke/press/news/chastnym-klientam/v-belarusbanke-poyavilsya-novyy-kredit-na-topovye-modeli-geely/",
            "https://belarusbank.by/o-banke/press/news/chastnym-klientam/belarusbank-zapuskaet-novyy-kredit-na-elektrokar-geely-so-stavkoy-ot-10/",
            "https://belarusbank.by/o-banke/press/news/chastnym-klientam/belarusbank-zapuskaet-novuyu-programmu-kreditovaniya-avtomobiley-belgee/",
            "https://belarusbank.by/o-banke/press/news/chastnym-klientam/stavki-tayut-etoy-vesnoy-u-belarusbanka-vygodnye-usloviya-po-kreditam-na-turisticheskie-i-meditsinsk/",
            "https://belarusbank.by/o-banke/press/news/chastnym-klientam/den-semi-s-belarusbankom-vygodnye-kredity-na-pokupki-i-puteshestviya-po-rodnoy-strane/",
        ],
    },
    {
        "filename": "karta-nesovershennoletnego-belarusbank.txt",
        "title": "Карта несовершеннолетнему Беларусбанка",
        "urls": [
            "https://belarusbank.by/fizicheskim_licam/cards/uchenik-belcart/",
            "https://belarusbank.by/fizicheskim_licam/cards/oformlenie_karty_uchashchegosya_za_4_shaga/",
            "https://belarusbank.by/fizicheskim_licam/cards/oformlenie_karty_uchashchegosya_internet_bankinge/",
            "https://belarusbank.by/fizicheskim_licam/cards/osobennosti_otkrytiya_tekushchikh_schetov_s_ispolzovaniem_kartochek_na_imya_nesovershennoletnikh/",
            "https://belarusbank.by/fizicheskim_licam/cards/zebra/",
            "https://belarusbank.by/fizicheskim_licam/cards/student-belcart/",
            "https://belarusbank.by/fizicheskim_licam/cards/zayavka-karta-study/",
            "https://belarusbank.by/fizicheskim_licam/online_services/mobilnoe-prilozhenie-mobiteen/",
            "https://belarusbank.by/o-banke/press/news/chastnym-klientam/leto-deti-i-finansovaya-svoboda-s-kartochkami-belarusbanka/",
        ],
    },
    {
        "filename": "oplata-telefonom-nfc-belarusbank.txt",
        "title": "Оплата телефоном / NFC Беларусбанка",
        "urls": [
            "https://belarusbank.by/fizicheskim_licam/online_services/",
            "https://belarusbank.by/fizicheskim_licam/online_services/apple-pay/",
            "https://belarusbank.by/fizicheskim_licam/online_services/samsung-pay/",
            "https://belarusbank.by/fizicheskim_licam/online_services/garmin-pay/",
            "https://belarusbank.by/fizicheskim_licam/online_services/belkart-pay/",
            "https://belarusbank.by/fizicheskim_licam/online_services/xiaomi-pay/",
            "https://belarusbank.by/fizicheskim_licam/online_services/swoo-pay/",
            "https://belarusbank.by/fizicheskim_licam/online_services/huawei-pay/",
            "https://belarusbank.by/fizicheskim_licam/cards/virtual-cards/",
        ],
    },
    {
        "filename": "perevod-v-rf-belarusbank.txt",
        "title": "Перевод в РФ Беларусбанка",
        "urls": [
            "https://belarusbank.by/fizicheskim_licam/bankovskie-perevody/",
            "https://belarusbank.by/docs/fizicheskim_licam/mezhdunarodnye-bankovskie-perevody-/",
            "https://belarusbank.by/docs/fizicheskim_licam/mezhdunarodnye-bankovskie-perevody-/309885/",
            "https://belarusbank.by/docs/fizicheskim_licam/mezhdunarodnye-bankovskie-perevody-/309887/",
            "https://belarusbank.by/fizicheskim_licam/bankovskie-perevody/trebovaniyami_valyutnogo_zakonodatelstva/",
            "https://belarusbank.by/fizicheskim_licam/bankovskie-perevody/vypiska_iz_sbornika_voznagrazhdeniy/",
            "https://belarusbank.by/fizicheskim_licam/cards/perevody_denezhnykh_sredstv_s_ispolzovaniem_kartochek/",
            "https://belarusbank.by/fizicheskim_licam/cards/vozmozhnye_ogranicheniya_pri_sovershenii_nekotorykh_operatsiy_s_ispolzovaniem_kartochek_banka/",
            "https://belarusbank.by/fizicheskim_licam/online_services/sistema-mgnovennykh-platezhey/",
            "https://belarusbank.by/fizicheskim_licam/online_services/perevody-po-nomeru-telefona-visa/",
            "https://belarusbank.by/fizicheskim_licam/online_services/pravila_predostavleniya/",
        ],
    },
]


def compile_topic(topic: dict) -> tuple[str, list[str], int]:
    blocks: list[str] = []
    used_urls: list[str] = []
    errors: list[str] = []
    seen_text: set[str] = set()
    ok = 0

    for url in topic["urls"]:
        title, text, error = fetch_page(url)
        time.sleep(0.25)
        if error:
            # Prefer RU X80 news; keep /be/ only if RU failed.
            if "/be/" in url and any(u.endswith(url.split("/be/", 1)[-1]) for u in used_urls):
                continue
            errors.append(f"{url} -> {error}")
            print(f"  SKIP {error}: {url}")
            continue
        fingerprint = " ".join(text.split())[:400]
        if fingerprint in seen_text:
            print(f"  DUP skip: {url}")
            continue
        seen_text.add(fingerprint)
        used_urls.append(url)
        ok += 1
        blocks.append(
            f"TITLE: {title or url}\n"
            f"URL: {url}\n"
            f"{'=' * 60}\n\n"
            f"{text.strip()}\n"
        )
        print(f"  OK [{len(text)} chars] {title or url}")

    header = [
        topic["title"],
        "",
        f"Дата сбора: {COLLECTED}",
        HEADER_NOTE,
        "",
        "Исходные ссылки:",
        *[f"- {u}" for u in used_urls],
        "",
        "=" * 60,
        "",
    ]
    body = "\n\n".join(blocks)
    return "\n".join(header) + body + "\n", errors, ok


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total_ok = 0
    all_errors: list[str] = []
    for topic in TOPICS:
        print(f"\n=== {topic['title']} ===")
        content, errors, ok = compile_topic(topic)
        path = OUT_DIR / topic["filename"]
        path.write_text(content, encoding="utf-8")
        print(f"Wrote {path} ({path.stat().st_size} bytes, {ok} pages)")
        total_ok += ok
        all_errors.extend(errors)
    print(f"\nDone: {total_ok} pages, {len(all_errors)} skipped")
    return 0 if total_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
