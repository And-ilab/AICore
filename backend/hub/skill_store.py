"""Org/user slash-skill library. Isolated from AssistantCapability / Task prompts."""

from __future__ import annotations

import re
from typing import Any, Mapping

from django.db import IntegrityError, transaction

from hub.models import AssistantSkill

ALIAS_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9\-]+$")

ORG_SKILL_PREFIX = (
    "Отвечай по-русски, канцелярски нейтрально; не выдумывай ФИО, даты, "
    "номера, суммы, должности, пункты регламента; нет в источнике — пиши "
    "«в предоставленных материалах не указано»; не обещай решений банка; "
    "ПДн не повторяй сверх необходимого."
)

SEED_ORG_SKILLS: tuple[dict[str, Any], ...] = (
    {
        "code": "SKL-01",
        "name": "Служебная записка",
        "alias": "записка",
        "needs_attachment": False,
        "instruction": (
            "Ты оформляешь служебную записку работника ОАО «АСБ Беларусбанк».\n\n"
            "По сообщению пользователя и вложениям собери черновик со структурой:\n\n"
            "Кому (должность, подразделение, ФИО — только если даны).\n\n"
            "От кого (то же).\n\n"
            "Тема.\n\n"
            "Основание (номер/дата документа — только если есть в тексте или БЗ).\n\n"
            "Изложение фактов краткими абзацами.\n\n"
            "Прошу (конкретная просьба).\n\n"
            "Приложения — список, если вложения или пользователь их назвал.\n\n"
            "Не добавляй шапку с исходящим номером и датой регистрации, если "
            "пользователь их не указал. Не подставляй подпись-факсимиле. Если не "
            "хватает «кому» или «прошу» — задай одно уточнение, затем всё равно "
            "выдай черновик с пометками [указать]."
        ),
    },
    {
        "code": "SKL-02",
        "name": "Справка по нормативке",
        "alias": "справка",
        "needs_attachment": False,
        "instruction": (
            "Ты готовишь внутреннюю справку по нормативному документу или статье "
            "базы знаний.\n\n"
            "Используй только фрагменты из выбранной БЗ и вложений. Структура ответа:\n\n"
            "Предмет справки (одно предложение).\n\n"
            "Кто / что / в какой срок / на каком основании (пункты, названия документов).\n\n"
            "Цитата или близкий пересказ с указанием источника.\n\n"
            "Если правило не найдено или релевантность низкая — напиши, чего не "
            "хватает, не формулируй норму «по смыслу».\n\n"
            "Не давай юридических заключений и не сравнивай с законодательством, "
            "если этого нет в источниках. Блок «Источники» обязателен."
        ),
    },
    {
        "code": "SKL-03",
        "name": "Ответ на обращение",
        "alias": "обращение",
        "needs_attachment": False,
        "instruction": (
            "Ты готовишь черновик официального ответа на обращение (клиент или "
            "внутреннее письмо).\n\n"
            "Структура:\n\n"
            "Обращение (краткое содержание, без лишних ПДн).\n\n"
            "По существу: что можно ответить строго по БЗ и вложениям.\n\n"
            "Что необходимо от заявителя (документы, данные), если без этого "
            "ответ неполный.\n\n"
            "Следующий шаг (куда обратиться / какой срок), только если это есть "
            "в источнике.\n\n"
            "Тон вежливый, без разговорных оборотов, без извинений «от лица банка», "
            "если пользователь не просил. Не обещай одобрение кредита, выплату, "
            "отмену комиссии. Если тема вне БЗ — откажись формулировать "
            "содержательный ответ и перечисли, какие документы нужны."
        ),
    },
    {
        "code": "SKL-04",
        "name": "Пошаговая инструкция",
        "alias": "инструкция",
        "needs_attachment": False,
        "instruction": (
            "Ты составляешь пошаговую инструкцию для работника банка.\n\n"
            "Только действия, которые прямо следуют из БЗ или вложения. Формат:\n\n"
            "Цель процедуры (одна строка).\n\n"
            "Шаги: нумерация, кто выполняет, что делает, какой документ "
            "получает/передаёт.\n\n"
            "Результат шага (если указан в источнике).\n\n"
            "Куда нести / в какую систему — только если названо.\n\n"
            "Не добавляй «обычно так делают» и не сокращай обязательные шаги. "
            "Пробелы в регламенте помечай: «шаг в источнике не описан». "
            "Не ставь пустой следующий номер (не заканчивай список строкой «4.»)."
        ),
    },
    {
        "code": "SKL-05",
        "name": "Чеклист процесса",
        "alias": "чеклист",
        "needs_attachment": False,
        "instruction": (
            "Ты превращаешь описание процесса или регламент в чеклист для исполнителя.\n\n"
            "Выход — маркированный список:\n\n"
            "пункт (документ, согласование, срок, ответственный) — формулировка "
            "из источника.\n\n"
            "Группируй: «До начала», «В ходе», «По завершении», если это читается "
            "из текста. Не добавляй контрольные точки «для качества», которых нет "
            "в источнике. Если процесс неясен — сначала 1–2 уточняющих вопроса, "
            "затем чеклист по тому, что уже известно."
        ),
    },
    {
        "code": "SKL-06",
        "name": "Сравнить редакции",
        "alias": "сравнить",
        "needs_attachment": True,
        "instruction": (
            "Ты сравниваешь две редакции текста (файлы, вставки «было / стало»).\n\n"
            "Таблица:\n\n"
            "Фрагмент / тема\n\n"
            "Редакция А\n\n"
            "Редакция Б\n\n"
            "Суть изменения\n\n"
            "Риск или на кого влияет — только если это явно следует из текста "
            "(срок, сумма, обязанность, сторона).\n\n"
            "Не считай отличием перенос строки и простую перестановку абзацев "
            "без смены смысла. Не дописывай текст, которого нет ни в А, ни в Б. "
            "Если передан один документ — попроси вторую редакцию или якорь «было»."
        ),
    },
    {
        "code": "SKL-07",
        "name": "Извлечь реквизиты",
        "alias": "реквизиты",
        "needs_attachment": True,
        "instruction": (
            "Ты извлекаешь реквизиты из текста сообщения и вложений.\n\n"
            "Верни таблицу (и дублируй JSON): date, document_number, full_name, "
            "organization, amount, currency, id_document, other.\n\n"
            "Правила: значение только если оно явно в тексте; иначе «не найдено». "
            "Не нормализуй ФИО и названия «для красоты». Суммы копируй как в "
            "источнике (разделители, пропись). Некатегоризированное — в other "
            "списком. Если документ нечитаем — перечисли, каких полей не хватает, "
            "не угадывай."
        ),
    },
    {
        "code": "SKL-08",
        "name": "Официальный перевод RU↔EN",
        "alias": "перевод",
        "needs_attachment": False,
        "instruction": (
            "Ты официально переводишь банковский и канцелярский текст RU↔EN.\n\n"
            "Жёсткое правило направления:\n"
            "если сообщение пользователя в основном на русском — переведи на английский;\n"
            "если в основном на английском — переведи на русский.\n"
            "Даже если это вопрос или просьба, сначала дай перевод его текста "
            "на целевой язык. Не отвечай на исходном языке.\n\n"
            "Для каждого абзаца:\n\n"
            "Перевод.\n\n"
            "Исходный текст (для сверки).\n\n"
            "Термины (вклад, овердрафт, платёжная инструкция, правление, филиал) "
            "переводи устойчиво, не «улучшай» и не адаптируй под другую юрисдикцию. "
            "Не добавляй пояснений, которых нет в оригинале. Сохраняй нумерацию "
            "пунктов и таблиц. Имена собственные и реквизиты не переводи, кроме "
            "устоявшихся названий банка, если пользователь не просил иное."
        ),
    },
    {
        "code": "SKL-09",
        "name": "Коротко",
        "alias": "кратко",
        "needs_attachment": False,
        "instruction": (
            "Ответь максимум двумя короткими предложениями. "
            "Без списков, без заголовков, без канцелярита. "
            "Скажи только суть."
        ),
    },
)


class SkillStoreError(ValueError):
    """Invalid skill payload or uniqueness violation."""


class SkillNotFound(SkillStoreError):
    """Skill is missing or not visible to the caller."""


class SkillNotAvailable(SkillStoreError):
    """Requested skill cannot be used in chat."""


def normalize_alias(raw: Any) -> str:
    if not isinstance(raw, str):
        raise SkillStoreError("alias must be a string")
    alias = raw.strip().lstrip("/")
    if not alias:
        raise SkillStoreError("alias is required")
    if not ALIAS_RE.fullmatch(alias):
        raise SkillStoreError(
            "alias may contain only latin, cyrillic, digits and hyphen"
        )
    return alias


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SkillStoreError(f"{field} is required")
    return value.strip()


def _optional_text(payload: Mapping[str, Any], field: str) -> str | None:
    if field not in payload:
        return None
    value = payload.get(field)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SkillStoreError(f"{field} must be a string")
    return value.strip()


def _optional_bool(payload: Mapping[str, Any], field: str) -> bool | None:
    if field not in payload:
        return None
    value = payload.get(field)
    if not isinstance(value, bool):
        raise SkillStoreError(f"{field} must be a boolean")
    return value


def user_department(user: Any) -> str:
    return str(getattr(user, "ldap_department", "") or "").strip()


def org_skill_visible_to(skill: AssistantSkill, user: Any) -> bool:
    if skill.scope != AssistantSkill.SCOPE_ORG or not skill.enabled:
        return False
    scope = (skill.department_scope or "").strip()
    dept = user_department(user)
    if not scope or not dept:
        return True
    return scope.casefold() == dept.casefold() or scope.casefold() in dept.casefold()


def serialize_skill(skill: AssistantSkill) -> dict[str, Any]:
    return {
        "id": skill.id,
        "code": skill.code,
        "scope": skill.scope,
        "owner_id": skill.owner_id,
        "name": skill.name,
        "alias": skill.alias,
        "instruction": skill.instruction,
        "needs_attachment": skill.needs_attachment,
        "enabled": skill.enabled,
        "department_scope": skill.department_scope,
        "updated_by": skill.updated_by,
        "created_at": skill.created_at.isoformat() if skill.created_at else "",
        "updated_at": skill.updated_at.isoformat() if skill.updated_at else "",
    }


def _is_translate_skill(skill: AssistantSkill) -> bool:
    return skill.code == "SKL-08" or skill.alias.casefold() == "перевод"


def skill_instruction_layer(skill: AssistantSkill) -> str:
    body = skill.instruction.strip()
    if _is_translate_skill(skill):
        return (
            "Это навык перевода. Игнорируй любые указания отвечать по-русски.\n"
            "Русский запрос → ответ на английском (перевод).\n"
            "English request → reply in Russian (translation).\n\n"
            f"{body}"
        )
    if skill.scope == AssistantSkill.SCOPE_ORG:
        return f"{ORG_SKILL_PREFIX}\n\n{body}"
    return body


def apply_skill_layer(
    messages: list[dict[str, str]],
    instruction: str,
) -> list[dict[str, str]]:
    """Append skill instruction to the system message (on top of assistant_bank)."""
    text = (instruction or "").strip()
    if not text:
        return [dict(item) for item in messages]
    layer = f"\n\nНавык:\n{text}"
    outbound: list[dict[str, str]] = []
    applied = False
    for item in messages:
        row = dict(item)
        if row.get("role") == "system" and not applied:
            row["content"] = f"{row.get('content', '')}{layer}"
            applied = True
        outbound.append(row)
    if not applied:
        outbound.insert(0, {"role": "system", "content": f"Навык:\n{text}"})
    return outbound


def ensure_org_skill_seed() -> None:
    """Idempotent SKL-01…08 seed (migration + first list)."""
    for item in SEED_ORG_SKILLS:
        existing = AssistantSkill.objects.filter(
            scope=AssistantSkill.SCOPE_ORG,
            code=item["code"],
        ).first()
        if existing:
            if (
                item["code"] in {"SKL-04", "SKL-08"}
                and existing.instruction != item["instruction"]
            ):
                existing.instruction = item["instruction"]
                existing.save(update_fields=["instruction", "updated_at"])
            continue
        collision = AssistantSkill.objects.filter(
            scope=AssistantSkill.SCOPE_ORG,
            alias=item["alias"],
        ).exists()
        if collision:
            continue
        AssistantSkill.objects.create(
            code=item["code"],
            scope=AssistantSkill.SCOPE_ORG,
            owner=None,
            name=item["name"],
            alias=item["alias"],
            instruction=item["instruction"],
            needs_attachment=item["needs_attachment"],
            enabled=True,
            department_scope="",
            updated_by="system",
        )


def _assert_org_alias_free(alias: str, *, exclude_id: int | None = None) -> None:
    query = AssistantSkill.objects.filter(
        scope=AssistantSkill.SCOPE_ORG,
        alias__iexact=alias,
    )
    if exclude_id is not None:
        query = query.exclude(pk=exclude_id)
    if query.exists():
        raise SkillStoreError("alias already exists in org layer")


def _assert_user_alias_free(
    owner_id: int,
    alias: str,
    *,
    exclude_id: int | None = None,
) -> None:
    query = AssistantSkill.objects.filter(
        scope=AssistantSkill.SCOPE_USER,
        owner_id=owner_id,
        alias__iexact=alias,
    )
    if exclude_id is not None:
        query = query.exclude(pk=exclude_id)
    if query.exists():
        raise SkillStoreError("alias already exists in user layer")


def list_org_skills() -> list[dict[str, Any]]:
    ensure_org_skill_seed()
    return [
        serialize_skill(item)
        for item in AssistantSkill.objects.filter(scope=AssistantSkill.SCOPE_ORG)
    ]


def get_org_skill(skill_id: int) -> AssistantSkill:
    try:
        return AssistantSkill.objects.get(
            pk=skill_id,
            scope=AssistantSkill.SCOPE_ORG,
        )
    except AssistantSkill.DoesNotExist as exc:
        raise SkillNotFound("skill not found") from exc


def create_org_skill(
    payload: Mapping[str, Any],
    *,
    username: str,
) -> dict[str, Any]:
    ensure_org_skill_seed()
    name = _required_text(payload, "name")
    alias = normalize_alias(payload.get("alias"))
    instruction = _required_text(payload, "instruction")
    needs_attachment = _optional_bool(payload, "needs_attachment")
    enabled = _optional_bool(payload, "enabled")
    department_scope = _optional_text(payload, "department_scope") or ""
    code = (_optional_text(payload, "code") or "").strip()
    _assert_org_alias_free(alias)
    if code and AssistantSkill.objects.filter(code=code).exists():
        raise SkillStoreError("code already exists")
    try:
        with transaction.atomic():
            skill = AssistantSkill.objects.create(
                code=code,
                scope=AssistantSkill.SCOPE_ORG,
                owner=None,
                name=name,
                alias=alias,
                instruction=instruction,
                needs_attachment=bool(needs_attachment),
                enabled=True if enabled is None else enabled,
                department_scope=department_scope,
                updated_by=username,
            )
    except IntegrityError as exc:
        raise SkillStoreError("alias already exists in org layer") from exc
    return serialize_skill(skill)


def update_org_skill(
    skill_id: int,
    payload: Mapping[str, Any],
    *,
    username: str,
) -> dict[str, Any]:
    skill = get_org_skill(skill_id)
    if "name" in payload:
        skill.name = _required_text(payload, "name")
    if "alias" in payload:
        alias = normalize_alias(payload.get("alias"))
        _assert_org_alias_free(alias, exclude_id=skill.id)
        skill.alias = alias
    if "instruction" in payload:
        skill.instruction = _required_text(payload, "instruction")
    needs_attachment = _optional_bool(payload, "needs_attachment")
    if needs_attachment is not None:
        skill.needs_attachment = needs_attachment
    enabled = _optional_bool(payload, "enabled")
    if enabled is not None:
        skill.enabled = enabled
    department_scope = _optional_text(payload, "department_scope")
    if department_scope is not None:
        skill.department_scope = department_scope
    skill.updated_by = username
    try:
        with transaction.atomic():
            skill.save()
    except IntegrityError as exc:
        raise SkillStoreError("alias already exists in org layer") from exc
    return serialize_skill(skill)


def delete_org_skill(skill_id: int) -> None:
    skill = get_org_skill(skill_id)
    skill.delete()


def list_catalog_for_user(user: Any) -> list[dict[str, Any]]:
    ensure_org_skill_seed()
    items: list[dict[str, Any]] = []
    for skill in AssistantSkill.objects.filter(scope=AssistantSkill.SCOPE_ORG):
        if org_skill_visible_to(skill, user):
            items.append(serialize_skill(skill))
    if getattr(user, "is_authenticated", False):
        for skill in AssistantSkill.objects.filter(
            scope=AssistantSkill.SCOPE_USER,
            owner=user,
        ):
            items.append(serialize_skill(skill))
    return items


def get_owned_skill(skill_id: int, user: Any) -> AssistantSkill:
    try:
        skill = AssistantSkill.objects.get(pk=skill_id)
    except AssistantSkill.DoesNotExist as exc:
        raise SkillNotFound("skill not found") from exc
    if skill.scope != AssistantSkill.SCOPE_USER or skill.owner_id != getattr(
        user, "pk", None
    ):
        raise SkillNotFound("skill not found")
    return skill


def create_user_skill(
    payload: Mapping[str, Any],
    *,
    user: Any,
) -> dict[str, Any]:
    name = _required_text(payload, "name")
    alias = normalize_alias(payload.get("alias"))
    instruction = _required_text(payload, "instruction")
    needs_attachment = _optional_bool(payload, "needs_attachment")
    _assert_user_alias_free(user.pk, alias)
    try:
        with transaction.atomic():
            skill = AssistantSkill.objects.create(
                code="",
                scope=AssistantSkill.SCOPE_USER,
                owner=user,
                name=name,
                alias=alias,
                instruction=instruction,
                needs_attachment=bool(needs_attachment),
                enabled=True,
                department_scope="",
                updated_by=user.get_username(),
            )
    except IntegrityError as exc:
        raise SkillStoreError("alias already exists in user layer") from exc
    return serialize_skill(skill)


def update_user_skill(
    skill_id: int,
    payload: Mapping[str, Any],
    *,
    user: Any,
) -> dict[str, Any]:
    skill = get_owned_skill(skill_id, user)
    if "name" in payload:
        skill.name = _required_text(payload, "name")
    if "alias" in payload:
        alias = normalize_alias(payload.get("alias"))
        _assert_user_alias_free(user.pk, alias, exclude_id=skill.id)
        skill.alias = alias
    if "instruction" in payload:
        skill.instruction = _required_text(payload, "instruction")
    needs_attachment = _optional_bool(payload, "needs_attachment")
    if needs_attachment is not None:
        skill.needs_attachment = needs_attachment
    skill.updated_by = user.get_username()
    try:
        with transaction.atomic():
            skill.save()
    except IntegrityError as exc:
        raise SkillStoreError("alias already exists in user layer") from exc
    return serialize_skill(skill)


def delete_user_skill(skill_id: int, user: Any) -> None:
    skill = get_owned_skill(skill_id, user)
    skill.delete()


def resolve_visible_skill_instruction(skill_id: int, user: Any) -> str:
    try:
        skill = AssistantSkill.objects.get(pk=skill_id)
    except AssistantSkill.DoesNotExist as exc:
        raise SkillNotAvailable("skill_not_available") from exc
    if skill.scope == AssistantSkill.SCOPE_ORG:
        if not org_skill_visible_to(skill, user):
            raise SkillNotAvailable("skill_not_available")
        return skill_instruction_layer(skill)
    if skill.scope == AssistantSkill.SCOPE_USER and skill.owner_id == getattr(
        user, "pk", None
    ):
        return skill_instruction_layer(skill)
    raise SkillNotAvailable("skill_not_available")
