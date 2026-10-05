"""VII.5.1 C2 AD group names for the 13 I.4 / §2.4 roles (I.10).

Customer (ДИТ) still signs off final CNs (tz-unified VII.5 №4). Until then these
``BB_*`` working defaults fill C2 and are used when ``AUTH_BACKEND=ldaps``.
Override any or all via ``AUTH_LDAP_ROLE_GROUP_MAP_JSON``.
"""

from __future__ import annotations

from auth.roles import ROLE_DEFINITIONS


def c2_role_group_map() -> dict[str, str]:
    """Return role_code → AD group CN for all 13 contractual roles."""
    return {
        role.code: role.c2_ad_group
        for role in ROLE_DEFINITIONS
        if role.c2_ad_group
    }


# Eager snapshot for docs / diagnostics (must stay length 13).
C2_ROLE_GROUP_MAP: dict[str, str] = c2_role_group_map()

if len(C2_ROLE_GROUP_MAP) != 13:
    raise RuntimeError("C2 map must cover all 13 I.4 roles")
