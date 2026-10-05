import uuid

from django.db import migrations, models


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
                            "Льготное кредитование",
                        ],
                    },
                    {
                        "label": "Потребительские кредиты",
                        "children": [
                            "Потребительские кредиты",
                            "Потребительские кредиты (сопровождение)",
                            "Без темы запроса",
                        ],
                    },
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
            {
                "label": "ДБО и переводы",
                "children": [
                    "Интернет-банкинг",
                    "М-банкинг",
                    "Онлайн-банк",
                    "Крок",
                    "Платежи",
                    "Переводы Swift",
                    "Перевод с карты на карту",
                    "Перевод по IBAN",
                    "Переводы (сопровождение)",
                    "Без темы запроса",
                ],
            },
            {
                "label": "Дополнительные продукты",
                "children": [
                    "Страхование",
                    "Ценные бумаги",
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
        ],
    },
    {
        "label": "Услуга на запрос на сервис",
        "children": [
            {
                "label": "Асуит (SD)",
                "children": [
                    "Блокировка/разблокировка интернет-банкинга",
                    "Блокировка/разблокировка СДБО",
                    "Снятие ограничений по п/к",
                    "Проверка готовности карт в ЦСРУБ",
                    "Проверка ставки по кредиту в ЦСРУБ",
                    "Проверка наличия заявления на перечисление пенсии/пособия",
                    "АИС ИДО/Арест",
                    "Идентификация клиента в программе IW (БПЦ)",
                    "Задержанные (изъятые) карточки",
                    "Найденные карточки",
                    "Смс-оповещение",
                    "Рассылка СМС",
                    "Спорные ситуации",
                    "Противоправные (мошеннические действия)",
                    "Без темы запроса",
                    "Сбои в ДБО банка",
                    "Жалобы и предложения",
                ],
            },
        ],
    },
    { "label": "Сообщения", "children": [] },
    { "label": "Продажа", "children": [] },
    { "label": "Проведение разбирательств", "children": [] },
    { "label": "Запрос не выявлен", "children": [] },
    { "label": "Прочее", "children": [] },
]


def seed_topics(apps, schema_editor):
    TopicNode = apps.get_model("online_chat", "DialogCloseTopicNode")
    if TopicNode.objects.exists():
        return

    def walk(nodes, parent, prefix_path):
        for index, node_data in enumerate(nodes, start=1):
            if isinstance(node_data, str):
                label = str(node_data).strip()
                path = f"{prefix_path} / {label}" if prefix_path else label
                TopicNode.objects.create(
                    parent=parent,
                    label=label,
                    full_path=path,
                    sort_order=index * 10,
                    is_active=True,
                    is_selectable=True,
                )
            elif isinstance(node_data, dict):
                label = str(node_data["label"]).strip()
                path = f"{prefix_path} / {label}" if prefix_path else label
                children = node_data.get("children", [])
                is_selectable = not bool(children)
                created = TopicNode.objects.create(
                    parent=parent,
                    label=label,
                    full_path=path,
                    sort_order=index * 10,
                    is_active=True,
                    is_selectable=is_selectable,
                )
                walk(children, created, path)

    walk(DEFAULT_DIALOG_TOPIC_TREE, None, "")


class Migration(migrations.Migration):

    dependencies = [
        ("online_chat", "0022_work_schedule_day_overrides"),
    ]

    operations = [
        migrations.CreateModel(
            name="DialogCloseTopicNode",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("label", models.CharField(max_length=200)),
                ("full_path", models.CharField(blank=True, db_index=True, default="", max_length=512)),
                ("sort_order", models.IntegerField(db_index=True, default=100)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("is_selectable", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.CASCADE,
                        related_name="children",
                        to="online_chat.dialogclosetopicnode",
                    ),
                ),
            ],
            options={"ordering": ("sort_order", "label")},
        ),
        migrations.AlterField(
            model_name="dialog",
            name="close_topic",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.AddField(
            model_name="dialog",
            name="close_topic_node",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="dialogs",
                to="online_chat.dialogclosetopicnode",
            ),
        ),
        migrations.RunPython(seed_topics, migrations.RunPython.noop),
    ]