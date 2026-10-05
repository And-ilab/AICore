#!/usr/bin/env python3
"""Seed demo CC chunks into ingest.CCProductionChunk for local sufler demos.

Also lowers sufler_cc context_inclusion_threshold so stub embeddings
(EMBEDDING_MODE=stub) can pass the RAG gate in local demos.

Usage:

  cd infra
  docker compose cp ../tools/seed_cc_demo_kb.py backend:/tmp/seed_cc_demo_kb.py
  docker compose exec backend python /tmp/seed_cc_demo_kb.py
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path


def _bootstrap_django() -> None:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / "backend",
        Path("/app"),
        Path.cwd(),
    ]
    for backend in candidates:
        if (backend / "sufler" / "settings.py").exists():
            if str(backend) not in sys.path:
                sys.path.insert(0, str(backend))
            break
    else:
        print("Cannot find Django backend (sufler/settings.py)", file=sys.stderr)
        raise SystemExit(2)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")
    import django

    django.setup()


_bootstrap_django()

from hub.models import ModelRegistrySettings  # noqa: E402
from ingest.models import CCProductionChunk  # noqa: E402
from core.embeddings import deterministic_embedding, embed_passage  # noqa: E402


# Each content starts with title + typical client question so stub embeddings
# overlap well with demo queries.
# Permalinks must be real belarusbank.by pages (checked 200 OK).
# Fake paths like /ru/fizicheskim_licam/cards/limity return 404.
DEMO_CHUNKS = [
    {
        "article_id": 91001,
        "title": "Лимиты снятия наличных",
        "permalink": "https://belarusbank.by/fizicheskim_licam/cards/otmena_ogranicheniy_po_karte/",
        "content": (
            "Лимиты снятия наличных в банкоматах Беларусбанка. "
            "Суточный лимит снятия наличных в банкоматах ОАО «АСБ Беларусбанк» "
            "для дебетовых карт составляет 2 000 BYN. Для кредитных карт лимит "
            "зависит от доступного кредитного лимита. Лимит обнуляется в 00:00 "
            "по минскому времени. При превышении операция будет отклонена. "
            "Альтернативы: касса отделения, безналичный перевод."
        ),
    },
    {
        "article_id": 91002,
        "title": "Комиссии банкоматов",
        "permalink": "https://belarusbank.by/fizicheskim_licam/cards/",
        "content": (
            "Комиссии банкоматов. Комиссия за снятие наличных в банкоматах "
            "Беларусбанка для карт банка не взимается в пределах тарифа. "
            "Комиссия за снятие в банкоматах других банков — от 1,5% от суммы, "
            "минимум 3 BYN. Тариф зависит от типа карты и банка-эмитента."
        ),
    },
    {
        "article_id": 91003,
        "title": "Открытие вклада",
        "permalink": "https://belarusbank.by/fizicheskim_licam/vklady/",
        "content": (
            "Открытие вклада. Как открыть вклад? Как открыть вклад в Беларусбанке? "
            "Открыть вклад можно в отделении и дистанционно. "
            "Для открытия вклада нужны паспорт и текущий счёт. Доступны "
            "вклады в BYN и валюте. Условия по ставке зависят от срока "
            "и продукта. Клиент может оформить вклад в отделении или "
            "в интернет-банке."
        ),
    },
    {
        "article_id": 91004,
        "title": "Блокировка карты",
        "permalink": "https://belarusbank.by/fizicheskim_licam/cards/uslugi_globalnoy_podderzhki_derzhateley_kartochek/",
        "content": (
            "Блокировка карты. Как заблокировать карту? Как заблокировать карту "
            "Беларусбанка при утрате или краже? "
            "Карту можно заблокировать в мобильном приложении, интернет-банке "
            "или по телефону контакт-центра 147. После блокировки операции "
            "по карте недоступны. Для выпуска новой карты обратитесь в отделение "
            "с паспортом."
        ),
    },
    {
        "article_id": 91005,
        "title": "Пин-код карты",
        "permalink": "https://belarusbank.by/fizicheskim_licam/cards/pravila_polzovaniya_kartochkoy_1/",
        "content": (
            "Пин-код карты. Как изменить или восстановить ПИН-код карты? "
            "Смена ПИН-кода доступна в банкомате Беларусбанка при наличии карты. "
            "Если ПИН забыт, оформите перевыпуск карты в отделении. "
            "Не сообщайте ПИН третьим лицам и оператору чата."
        ),
    },
    {
        "article_id": 91006,
        "title": "Интернет-банк",
        "permalink": "https://belarusbank.by/fizicheskim_licam/online_services/internet-banking/",
        "content": (
            "Интернет-банк. Как подключить интернет-банк? Как подключить "
            "интернет-банк Беларусбанка? Подключение выполняется в отделении "
            "банка или через мобильное приложение при наличии карты. Для входа "
            "нужен логин и пароль. При утере доступа восстановите пароль на "
            "сайте или в отделении."
        ),
    },
    {
        "article_id": 91007,
        "title": "Перевод по номеру телефона",
        "permalink": "https://belarusbank.by/fizicheskim_licam/online_services/m-banking/",
        "content": (
            "Перевод по номеру телефона. Как перевести деньги по номеру телефона? "
            "В приложении Беларусбанка выберите перевод по номеру телефона, "
            "укажите получателя и сумму. Лимиты зависят от тарифа и статуса "
            "клиента. Комиссия отображается до подтверждения операции."
        ),
    },
    {
        "article_id": 91008,
        "title": "Кредитная карта",
        "permalink": "https://belarusbank.by/fizicheskim_licam/kredit/",
        "content": (
            "Кредитная карта. Как оформить кредитную карту Беларусбанка? "
            "Подайте заявку в отделении или онлайн. Потребуются паспорт и "
            "сведения о доходах. Решение принимается после проверки. "
            "Льготный период и ставка зависят от выбранного продукта."
        ),
    },
    {
        "article_id": 91009,
        "title": "Реквизиты для перевода",
        "permalink": "https://belarusbank.by/fizicheskim_licam/online_services/internet-banking/",
        "content": (
            "Реквизиты для перевода. Где взять реквизиты счёта Беларусбанка? "
            "Реквизиты доступны в интернет-банке, мобильном приложении "
            "и в отделении. Для перевода из другого банка нужны IBAN, "
            "БИК и назначение платежа. Уточните валюту счёта перед переводом."
        ),
    },
    {
        "article_id": 91010,
        "title": "График работы отделений",
        "permalink": "https://belarusbank.by/map/",
        "content": (
            "График работы отделений. Какой режим работы отделений Беларусбанка? "
            "Большинство отделений работают в будни с 09:00 до 19:00, "
            "в субботу — сокращённый день. Точный график зависит от отделения. "
            "Актуальные часы смотрите на сайте банка в разделе отделений."
        ),
    },
    {
        "article_id": 91011,
        "title": "SMS-оповещения",
        "permalink": "https://belarusbank.by/fizicheskim_licam/online_services/razblokirovka_po_sms/",
        "content": (
            "SMS-оповещения. Как подключить SMS по операциям карты? "
            "Услуга подключается в интернет-банке, приложении или отделении. "
            "Оповещения приходят на номер, привязанный к карте. "
            "Тариф услуги зависит от пакета обслуживания."
        ),
    },
    {
        "article_id": 91013,
        "title": "Переводы в РФ",
        "permalink": "https://belarusbank.by/fizicheskim_licam/online_services/m-banking/",
        "content": (
            "Переводы в РФ. Как оформить перевод в Россию через мобильный банк? "
            "Перевод в РФ доступен через «Платежи» → «За рубеж». "
            "Проверьте суточный лимит клиента и статус карты. "
            "Для перевода нужен действующий лимит на международные операции. "
            "Комиссия зависит от суммы и валюты."
        ),
    },
    {
        "article_id": 91012,
        "title": "Закрытие счёта",
        "permalink": "https://belarusbank.by/o-banke/press/kontakt-centr/",
        "content": (
            "Закрытие счёта. Как закрыть текущий счёт в Беларусбанке? "
            "Обратитесь в отделение с паспортом. Перед закрытием погасите "
            "задолженности и переведите остаток. Карты, привязанные к счёту, "
            "будут заблокированы."
        ),
    },
]

DEMO_CONTEXT_THRESHOLD = 0.33


def _ensure_sufler_threshold() -> None:
    settings = ModelRegistrySettings.objects.filter(profile="sufler_cc").first()
    if settings is None:
        print("warn: ModelRegistrySettings(sufler_cc) missing — skip threshold")
        return
    if settings.context_inclusion_threshold <= DEMO_CONTEXT_THRESHOLD:
        print(
            f"threshold ok={settings.context_inclusion_threshold} "
            f"(deterministic={settings.deterministic_answer_threshold})"
        )
        return
    settings.context_inclusion_threshold = DEMO_CONTEXT_THRESHOLD
    if settings.deterministic_answer_threshold < DEMO_CONTEXT_THRESHOLD:
        settings.deterministic_answer_threshold = DEMO_CONTEXT_THRESHOLD
    settings.revision = int(settings.revision or 1) + 1
    settings.save()
    print(
        f"threshold set={settings.context_inclusion_threshold} "
        f"deterministic={settings.deterministic_answer_threshold}"
    )


def _embed(text: str) -> list[float]:
    try:
        return embed_passage(text)
    except Exception:
        return deterministic_embedding(text)


def main() -> int:
    _ensure_sufler_threshold()
    created = 0
    updated = 0
    for item in DEMO_CHUNKS:
        checksum = hashlib.sha256(item["content"].encode("utf-8")).hexdigest()
        obj, was_created = CCProductionChunk.objects.update_or_create(
            article_id=item["article_id"],
            chunk_index=0,
            defaults={
                "version_id": 1,
                "title": item["title"],
                "permalink": item["permalink"],
                "content": item["content"],
                "locale": "ru",
                "visibility_scope": ["kc_operator"],
                "checksum": f"sha256:{checksum}",
                "embedding_model": "deterministic-dev",
                "embedding": _embed(item["content"]),
                "is_active": True,
            },
        )
        created += int(was_created)
        updated += int(not was_created)
        print(f"{'create' if was_created else 'update'} {obj.article_id} {obj.title}")
    print(
        f"done created={created} updated={updated} "
        f"total={CCProductionChunk.objects.count()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
