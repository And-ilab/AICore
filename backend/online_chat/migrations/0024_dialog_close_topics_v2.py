"""Reseed DialogCloseTopicNode with the exact hierarchy from "тематики 2026.xlsx"
(sheet "Физ. лица"): Тип запроса -> Тема запроса -> Вид запроса -> Вид запроса.

Migration 0023 seeded a first draft, but its `seed_topics` guarded on
`TopicNode.objects.exists()`, so a later edit of the tree never re-applied to
already-provisioned databases. This migration always clears the table and
rebuilds it from the corrected source-of-truth tree.
"""
from __future__ import annotations

from django.db import migrations


# Nested structure: a dict has "label" + "children"; a bare string is a leaf.
# Order follows the "Физ. лица" sheet of тематики 2026.xlsx exactly.
DEFAULT_DIALOG_TOPIC_TREE = [
    {
        "label": "Консультация по продукту или услуге",
        "children": [
            {
                "label": "Вклады",
                "children": [
                    "Безотзывные депозиты",
                    "Отзывные депозиты",
                    "Семейный капитал",
                    "Текущие счета",
                    "Базовые счета",
                    "Вклады (сопровождение)",
                    "Без темы запроса",
                ],
            },
            {
                "label": "Кредиты",
                "children": [
                    {
                        "label": "На недвижимость",
                        "children": [
                            "Покупка жилых помещений",
                            "Строительство жилых помещений",
                            "Система строительных сбережений",
                            "Реконструкция",
                            "Кредиты на недвижимость (сопровождение)",
                        ],
                    },
                    "Льготное кредитование",
                    {
                        "label": "Потребительские кредиты",
                        "children": [
                            "Потребительские кредиты",
                            "Потребительские кредиты (сопровождение)",
                        ],
                    },
                    "Без темы запроса",
                ],
            },
            {
                "label": "Платежные карты",
                "children": [
                    "Блокировка/разблокировка карточек, баланс",
                    "Платежные карты, клубы",
                    "Утеря/перевыпуск/обновление карт",
                    "Операции с карточками/по счету",
                    "Услуги/приложения/сервисы",
                    "Овердрафт",
                    "Магнит",
                    "Платежные карточки (сопровождение)",
                    "Без темы запроса",
                ],
            },
            "Интернет-банкинг",
            "М-банкинг",
            "Онлайн-банк",
            "Крок",
            "Платежи",
            {
                "label": "Переводы",
                "children": [
                    "Swift",
                    "Перевод с карты на карту",
                    "Перевод по IBAN",
                    "Переводы (сопровождение)",
                    "Без темы запроса",
                ],
            },
            "Страхование",
            "Ценные бумаги",
            {
                "label": "Прочее",
                "children": [
                    "Адресная информация (отделения, банкоматы, инфокиоск)",
                    "Операции с валютой",
                    "Сейфы",
                    "Драгоценные металлы и камни, монеты",
                    "Прочая информация/услуги",
                    "Комиссии/тарифы",
                    "Англоязычная консультация",
                    "Без темы запроса",
                ],
            },
            "Без темы запроса",
        ],
    },
    {
        "label": "Услуга на запрос на сервис",
        "children": [
            "Асуит (SD)",
            "Блокировка/разблокировка интернет-банкинга",
            "Блокировка/разблокировка СДБО",
            "Снятие ограничений по п/к",
            "Проверка готовности карт в ЦСРУБ",
            "Проверка ставки по кредиту в ЦСРУБ",
            "Проверка наличия заявления на перечисление пенсии/пособия",
            {
                "label": "Проведение разбирательств",
                "children": [
                    "АИС ИДО/Арест",
                    "Идентификация клиента в программе IW (БПЦ)",
                    "Задержанные (изъятые) карточки",
                    "Найденные карточки",
                    "Смс-оповещение",
                    "Рассылка СМС",
                    "Спорные ситуации",
                ],
            },
            "Противоправные (мошеннические действия)",
            "Без темы запроса",
        ],
    },
    {
        "label": "Сообщения",
        "children": [
            "Сбои в ДБО банка",
            "Жалобы и предложения",
            "Без темы запроса",
        ],
    },
    {
        "label": "Продажа",
        "children": [
            "Платежные карты",
            "Кредиты",
            "Прочие продукты/услуги",
            "Регламентные смс-рассылки Банка",
        ],
    },
    {
        "label": "Запрос не выявлен",
        "children": [],
    },
]


def reseed_topics(apps, schema_editor):
    TopicNode = apps.get_model("online_chat", "DialogCloseTopicNode")
    TopicNode.objects.all().delete()

    def walk(nodes, parent, prefix_path):
        for index, node_data in enumerate(nodes, start=1):
            if isinstance(node_data, str):
                label = node_data.strip()
                path = f"{prefix_path} / {label}" if prefix_path else label
                TopicNode.objects.create(
                    parent=parent,
                    label=label,
                    full_path=path,
                    sort_order=index * 10,
                    is_active=True,
                    is_selectable=True,
                )
            else:
                label = str(node_data["label"]).strip()
                path = f"{prefix_path} / {label}" if prefix_path else label
                children = node_data.get("children", [])
                created = TopicNode.objects.create(
                    parent=parent,
                    label=label,
                    full_path=path,
                    sort_order=index * 10,
                    is_active=True,
                    is_selectable=not bool(children),
                )
                walk(children, created, path)

    walk(DEFAULT_DIALOG_TOPIC_TREE, None, "")


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0023_dialog_close_topics"),
    ]

    operations = [
        migrations.RunPython(reseed_topics, migrations.RunPython.noop),
    ]
