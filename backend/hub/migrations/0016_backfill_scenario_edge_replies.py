import base64
from copy import deepcopy
import json
import zlib

from django.db import migrations


# Immutable snapshot of (scenario code, source node, target node, reply).
# Keeping the data in this migration avoids importing mutable runtime catalog code.
_REPLIES_ZLIB_BASE64 = (
    "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"
)

_REPLY_CORRECTIONS = {
    ("CC-SCR-001", "start", "with_card"): "Мне нужна карточка к счёту",
    ("CC-SCR-001", "start", "without_card"): "Мне нужен текущий счёт без карточки",
    ("CC-SCR-009", "start", "ul"): "Перевод будет делать юрлицо",
    ("CC-SCR-009", "start", "no_card"): "Нет карты, буду переводить без неё",
    ("CC-SCR-011", "start", "answer"): "В приложении карту ещё не блокировал, нужна блокировка оператором",
    ("CC-SCR-012", "start", "answer"): "Карту ещё не блокировал, после утери нужен перевыпуск",
    ("CC-SCR-013", "start", "answer"): "Истёк срок карты, нужен перевыпуск",
    ("CC-SCR-014", "start", "answer"): "Нужна виртуальная карта только для интернета",
    ("CC-SCR-015", "start", "answer"): "Нужен лимит на оплату в интернете",
    ("CC-SCR-016", "start", "answer"): "Это чужой банкомат, хочу снять пятьсот рублей",
    ("CC-SCR-017", "start", "answer"): "Номер не менялся, услуга SMS подключена",
    ("CC-SCR-018", "start", "answer"): "Оплата в интернете, номер актуальный, но код 3-D Secure не приходит",
    ("CC-SCR-019", "start", "answer"): "В магазине терминал показывает отказ в оплате",
    ("CC-SCR-020", "start", "answer"): "Пароль помню, но учётная запись заблокирована",
    ("CC-SCR-021", "start", "answer"): "В мобильном приложении возникает ошибка входа",
    ("CC-SCR-022", "start", "answer"): "Новый номер телефона нужен и для SMS, и для ДБО",
    ("CC-SCR-023", "start", "answer"): "Хочу оплачивать коммунальные услуги через ЕРИП",
    ("CC-SCR-024", "start", "answer"): "Хочу безналично обменять валюту в мобильном приложении",
    ("CC-SCR-025", "start", "answer"): "Перевод в евро в Германию, полные SWIFT-реквизиты есть",
    ("CC-SCR-026", "start", "answer"): "Зачисление будет из-за рубежа",
    ("CC-SCR-027", "start", "answer"): "Нужен вклад в белорусских рублях на год, открою онлайн",
    ("CC-SCR-028", "start", "answer"): "Вклад отзывный, хочу закрыть его досрочно, до срока два месяца",
    ("CC-SCR-029", "start", "answer"): "Интересует ставка по новому вкладу",
    ("CC-SCR-030", "start", "answer"): "Хочу закрыть счёт, остатка и ограничений нет, карта заблокирована",
    ("CC-SCR-031", "start", "answer"): "Это заявка на потребительский кредит, номер заявки у меня есть",
    ("CC-SCR-032", "start", "answer"): "Хочу внести плановый платёж по кредиту",
    ("CC-SCR-033", "start", "answer"): "Да, арест наложил судебный исполнитель, сумма известна",
    ("CC-SCR-034", "start", "answer"): "Справка нужна для визы на английском языке",
    ("CC-SCR-035", "start", "answer"): "Карта новая, выбрана доставка на дом",
    ("CC-SCR-036", "start", "answer"): "Кэшбэк не пришёл за покупку в супермаркете за прошлый месяц",
    ("CC-SCR-037", "start", "answer"): "Карта у меня, деньги уже списали и операция есть в SMS",
    ("CC-SCR-038", "start", "answer"): "Жалоба на обслуживание в отделении, ответ хочу получить письмом",
    ("CC-SCR-039", "start", "answer"): "Ищу отделение в Минске с кассовым узлом",
    ("CC-SCR-040", "start", "answer"): "Ищу ближайший банкомат, инцидента с устройством нет",
    ("CC-SCR-041", "start", "answer"): "Не могу распечатать выписку в инфокиоске",
    ("CC-SCR-042", "start", "answer"): "Да, свидетельство о праве на наследство есть",
    ("CC-SCR-043", "start", "answer"): "Нотариальная доверенность выдана на снятие наличных",
    ("CC-SCR-044", "start", "answer"): "Работодатель ещё не отправил зарплатный реестр",
    ("CC-SCR-045", "start", "answer"): "Карта для пенсии уже есть, заявление в фонд ещё не подавал",
    ("CC-SCR-046", "start", "answer"): "Хочу оформить карту рассрочки",
    ("CC-SCR-047", "start", "answer"): "Для оплаты за границей международные операции включены, 3-D Secure тоже",
    ("CC-SCR-048", "start", "answer"): "Изменилась фамилия и паспортные данные",
    ("CC-SCR-049", "start", "answer"): "Нужна история операций в файле для себя, без заверения",
    ("CC-SCR-050", "start", "answer"): "Операция уже прошла, хочу уточнить применённый курс",
}


def _catalog_replies():
    rows = json.loads(
        zlib.decompress(base64.b64decode(_REPLIES_ZLIB_BASE64)).decode("utf-8")
    )
    replies = {
        (code, source, target): reply for code, source, target, reply in rows
    }
    replies.update(_REPLY_CORRECTIONS)
    return replies


def backfill_scenario_edge_replies(apps, schema_editor):
    DialogScenario = apps.get_model("hub", "DialogScenario")
    replies = _catalog_replies()
    codes = {key[0] for key in replies}
    scenarios = DialogScenario.objects.select_related("current_version").filter(
        code__in=codes
    )
    for scenario in scenarios.iterator():
        version = scenario.current_version
        if version is None:
            continue
        graph = deepcopy(version.graph or {})
        changed = False
        for node in graph.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            source_id = str(node.get("id") or "")
            for edge in node.get("edges") or []:
                if (
                    not isinstance(edge, dict)
                    or str(edge.get("reply") or "").strip()
                ):
                    continue
                key = (scenario.code, source_id, str(edge.get("to") or ""))
                reply = replies.get(key)
                if reply:
                    edge["reply"] = reply
                    changed = True
        if changed:
            version.graph = graph
            version.save(update_fields=["graph"])


class Migration(migrations.Migration):
    dependencies = [
        ("hub", "0015_quarantine_corrupted_kb_text"),
    ]

    operations = [
        migrations.RunPython(
            backfill_scenario_edge_replies,
            migrations.RunPython.noop,
        ),
    ]
