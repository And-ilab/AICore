"""Contractual I.4 role, permission, and Hub-tab mapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from django.core.exceptions import ImproperlyConfigured


PERM_SYSTEM_ADMIN = "system.admin"
PERM_KB_ADMIN = "kb.admin"
PERM_QU_ADMIN = "qu.admin"
PERM_PROMPTS_ADMIN = "prompts.admin"
PERM_CC_ADMIN = "cc.admin"
PERM_RBAC_ADMIN = "rbac.admin"
PERM_INTEGRATIONS_ADMIN = "integrations.admin"
PERM_SUFLER_TELEPHONY = "sufler.telephony.use"
PERM_SUFLER_CHAT = "sufler.chat.use"
PERM_CC_TEST_DIALOG = "cc.test_dialog.use"
PERM_CC_REPORTS = "cc.reports.view"
PERM_ASSISTANT_ADMIN = "assistant.admin"
PERM_ASSISTANT_USE = "assistant.use"
PERM_ASSISTANT_REPORTS = "assistant.reports.view"
PERM_OCR_ADMIN = "ocr.admin"
PERM_OCR_USE = "ocr.use"
PERM_OCR_REPORTS = "ocr.reports.view"


@dataclass(frozen=True)
class RoleDefinition:
    number: int
    code: str
    contractual_name: str
    mock_ad_group: str
    permissions: frozenset[str]
    tabs: tuple[str, ...]
    # VII.5.1 C2 working default (overridable via AUTH_LDAP_ROLE_GROUP_MAP_JSON).
    c2_ad_group: str = ""


def _role(
    number: int,
    code: str,
    contractual_name: str,
    mock_ad_group: str,
    permissions: frozenset[str],
    tabs: tuple[str, ...],
    c2_ad_group: str,
) -> RoleDefinition:
    return RoleDefinition(
        number,
        code,
        contractual_name,
        mock_ad_group,
        permissions,
        tabs,
        c2_ad_group,
    )


ROLE_DEFINITIONS = (
    _role(
        1,
        "software_administrator",
        "Администратор ПО",
        "Sufler_Role_01_SoftwareAdmin",
        frozenset({"*"}),
        (
            "hub",
            "settings",
            "integrations",
            "security",
            "kb_llm",
            "contact_center",
            "assistant",
            "ocr",
            "reports",
        ),
        "BB_AI_Software_Admin",
    ),
    _role(
        2,
        "llm_knowledge_base_administrator",
        "Администратор базы знаний LLM",
        "Sufler_Role_02_LLMKnowledgeAdmin",
        frozenset(
            {
                PERM_KB_ADMIN,
                PERM_QU_ADMIN,
                PERM_PROMPTS_ADMIN,
                PERM_ASSISTANT_ADMIN,
            }
        ),
        ("hub", "kb_llm", "qu", "prompts", "assistant_settings"),
        "BB_AI_LLM_KB_Admin",
    ),
    _role(
        3,
        "contact_center_module_administrator",
        "Администратор модуля Контакт-центра",
        "Sufler_Role_03_ContactCenterAdmin",
        frozenset(
            {
                PERM_CC_ADMIN,
                PERM_RBAC_ADMIN,
                PERM_INTEGRATIONS_ADMIN,
                PERM_CC_REPORTS,
            }
        ),
        ("hub", "contact_center", "chat_queues", "rbac", "integrations", "cc_reports"),
        "BB_CC_Module_Admin",
    ),
    _role(
        4,
        "contact_center_telephony_operator",
        "Оператор канала телефония Контакт-центра",
        "Sufler_Role_04_TelephonyOperator",
        frozenset({PERM_SUFLER_TELEPHONY, PERM_ASSISTANT_USE}),
        ("hub", "sufler_telephony", "assistant"),
        "BB_CC_Telephony_Operator",
    ),
    _role(
        5,
        "contact_center_online_chat_operator",
        "Оператор онлайн-чата Контакт-центра",
        "Sufler_Role_05_OnlineChatOperator",
        frozenset({PERM_SUFLER_CHAT, PERM_ASSISTANT_USE}),
        ("hub", "sufler_chat", "assistant"),
        "BB_CC_Chat_Operator",
    ),
    _role(
        6,
        "contact_center_internal_user",
        "Внутренний пользователь Контакт-центра",
        "Sufler_Role_06_ContactCenterInternal",
        frozenset({PERM_CC_TEST_DIALOG}),
        ("hub", "cc_test_dialog"),
        "BB_CC_Internal_User",
    ),
    _role(
        7,
        "contact_center_analyst",
        "Аналитик Контакт-центра",
        "Sufler_Role_07_ContactCenterAnalyst",
        frozenset({PERM_CC_REPORTS}),
        ("hub", "cc_reports"),
        "BB_CC_Analyst",
    ),
    _role(
        8,
        "ai_assistant_module_administrator",
        "Администратор модуля ИИ-ассистент",
        "Sufler_Role_08_AssistantAdmin",
        frozenset(
            {
                PERM_ASSISTANT_ADMIN,
                PERM_ASSISTANT_USE,
                PERM_INTEGRATIONS_ADMIN,
            }
        ),
        ("hub", "assistant", "assistant_settings", "assistant_sources"),
        "BB_AI_Assistant_Admin",
    ),
    _role(
        9,
        "ai_assistant_user",
        "Пользователь ИИ-ассистента",
        "Sufler_Role_09_AssistantUser",
        frozenset({PERM_ASSISTANT_USE}),
        ("hub", "assistant"),
        "BB_AI_Assistant_User",
    ),
    _role(
        10,
        "ai_assistant_analyst",
        "Аналитик ИИ-ассистента",
        "Sufler_Role_10_AssistantAnalyst",
        frozenset({PERM_ASSISTANT_REPORTS}),
        ("hub", "assistant_reports"),
        "BB_AI_Assistant_Analyst",
    ),
    _role(
        11,
        "document_recognition_module_administrator",
        "Администратор модуля распознавания документов",
        "Sufler_Role_11_OCRAdmin",
        frozenset({PERM_OCR_ADMIN, PERM_OCR_USE}),
        ("hub", "ocr", "ocr_settings"),
        "BB_IDP_Admin",
    ),
    _role(
        12,
        "document_recognition_user",
        "Пользователь модуля распознавания документов",
        "Sufler_Role_12_OCRUser",
        frozenset({PERM_OCR_USE}),
        ("hub", "ocr"),
        "BB_IDP_User",
    ),
    _role(
        13,
        "document_recognition_analyst",
        "Аналитик модуля распознавания документов",
        "Sufler_Role_13_OCRAnalyst",
        frozenset({PERM_OCR_REPORTS}),
        ("hub", "ocr_reports"),
        "BB_IDP_Analyst",
    ),
)

ROLES_BY_CODE = {role.code: role for role in ROLE_DEFINITIONS}
ROLES_BY_GROUP = {
    role.mock_ad_group.casefold(): role for role in ROLE_DEFINITIONS
}
# Also index C2 AD CNs so prod mirrored groups resolve without JSON alone.
for _role_def in ROLE_DEFINITIONS:
    if _role_def.c2_ad_group:
        ROLES_BY_GROUP[_role_def.c2_ad_group.casefold()] = _role_def
ALL_PERMISSIONS = frozenset(
    permission
    for role in ROLE_DEFINITIONS
    for permission in role.permissions
    if permission != "*"
)
ALL_TABS = tuple(
    dict.fromkeys(
        tab for role in ROLE_DEFINITIONS for tab in role.tabs
    )
)

if len(ROLE_DEFINITIONS) != 13:
    raise RuntimeError("I.4 requires exactly 13 contractual roles")
if len(ROLES_BY_CODE) != 13:
    raise RuntimeError("I.4 role codes must be unique")
_mock_groups = {role.mock_ad_group.casefold() for role in ROLE_DEFINITIONS}
_c2_groups = {role.c2_ad_group.casefold() for role in ROLE_DEFINITIONS}
if len(_mock_groups) != 13 or len(_c2_groups) != 13:
    raise RuntimeError("I.4 mock and C2 AD groups must be unique")
if _mock_groups & _c2_groups:
    raise RuntimeError("I.4 mock and C2 AD group namespaces must not overlap")


def role_codes_from_group_names(
    group_names: Iterable[str],
    role_group_map: dict[str, str] | None = None,
) -> frozenset[str]:
    configured_groups = {
        group_name.casefold(): role_code
        for role_code, group_name in (role_group_map or {}).items()
        if role_code in ROLES_BY_CODE
        and isinstance(group_name, str)
        and group_name
    }
    roles = {
        (
            configured_groups.get(group_name.casefold())
            or role.code
        )
        for group_name in group_names
        if (role := ROLES_BY_GROUP.get(group_name.casefold())) is not None
        or group_name.casefold() in configured_groups
    }
    return frozenset(roles)


def role_codes_for_user(user: Any) -> frozenset[str]:
    if not getattr(user, "is_authenticated", False):
        return frozenset()
    if getattr(user, "is_superuser", False):
        return frozenset(ROLES_BY_CODE)
    cached = getattr(user, "_sufler_rbac_roles", None)
    if cached is not None:
        return frozenset(cached)
    try:
        group_names = user.groups.values_list("name", flat=True)
    except (AttributeError, TypeError):
        group_names = ()
    try:
        from django.conf import settings

        role_group_map = getattr(
            settings,
            "AUTH_LDAP_ROLE_GROUP_MAP",
            {},
        )
    except ImproperlyConfigured:
        role_group_map = {}
    roles = role_codes_from_group_names(group_names, role_group_map)
    user._sufler_rbac_roles = roles
    return roles


def permissions_for_user(user: Any) -> frozenset[str]:
    if getattr(user, "is_superuser", False):
        return frozenset({"*", *ALL_PERMISSIONS})
    permissions = {
        permission
        for role_code in role_codes_for_user(user)
        for permission in ROLES_BY_CODE[role_code].permissions
    }
    if "*" in permissions:
        permissions.update(ALL_PERMISSIONS)
    return frozenset(permissions)


def has_permission(user: Any, permission: str) -> bool:
    permissions = permissions_for_user(user)
    return "*" in permissions or permission in permissions


def tabs_for_user(user: Any) -> tuple[str, ...]:
    if getattr(user, "is_superuser", False):
        return ALL_TABS
    allowed = {
        tab
        for role_code in role_codes_for_user(user)
        for tab in ROLES_BY_CODE[role_code].tabs
    }
    return tuple(tab for tab in ALL_TABS if tab in allowed)
