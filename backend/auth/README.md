# Authentication and I.4 / I.10 RBAC

`backend/auth/` is a plain Python package, not an installed Django app.
`django.contrib.auth` already uses the app label `auth`; registering a second
app with that label would break Django startup.

## Portal auth context

The frontend launcher reads the current Django session and I.4 role codes from
`GET /api/auth/me/`. Anonymous users receive `authenticated: false` and an empty
`roles` list, so the launcher and protected module routes remain hidden.

Session login for ops / I.10 smoke:

- `POST /api/auth/login/` — JSON `{"username","password"}` → session cookie
- `POST /api/auth/logout/`

## Modes (`AUTH_BACKEND`)

`AUTH_BACKEND` selects the Django authentication backend (I.10 prod cutover).
`AUTH_MODE` remains a legacy alias (`ldap` → `ldaps`).

| Value | Backend | Use |
| --- | --- | --- |
| `mock_ldap` | `MockLDAPBackend` (P2-01) | Local / CI (`DJANGO_DEBUG=true`) |
| `ldaps` | `django_auth_ldap.LDAPBackend` | Bank TEST / PROD |
| `model` | `ModelBackend` | Rare fallback |

Default: `mock_ldap` when `DJANGO_DEBUG=true`, otherwise `model`.

### Development mock LDAP (P2-01)

```powershell
$env:AUTH_BACKEND = "mock_ldap"
$env:AUTH_MOCK_LDAP_DEFAULT_PASSWORD = "local-dev-secret"
python manage.py runserver
```

Default directory: `dev-role-01` … `dev-role-13` (one per I.4 role), groups
`Sufler_Role_*`. Mock never stores the password on the Django user.
`AUTH_MOCK_LDAP_USERS_JSON` may supply custom records.

When `DEBUG=false`, mock auth returns no user unless
`AUTH_MOCK_LDAP_ALLOW_INSECURE=true` (tests only).

### Production LDAPS (I.10, replaces mock on TEST/PROD)

```env
AUTH_BACKEND=ldaps
AUTH_LDAP_SERVER_URI=ldaps://ad.bank.local:636
AUTH_LDAP_BIND_DN=CN=svc-sufler,OU=Service,DC=bank,DC=local
AUTH_LDAP_BIND_PASSWORD=secret-from-vault
AUTH_LDAP_USER_SEARCH_BASE=OU=Users,DC=bank,DC=local
AUTH_LDAP_GROUP_SEARCH_BASE=OU=Groups,DC=bank,DC=local
AUTH_LDAP_USER_FILTER=(sAMAccountName=%(user)s)
AUTH_LDAP_TLS_CACERTFILE=/etc/ssl/certs/bank-ad-ca.pem
# Optional C2 overrides (role_code → approved AD CN):
# AUTH_LDAP_ROLE_GROUP_MAP_JSON={"ai_assistant_user":"BANK_APPROVED_USERS"}
```

Install on Linux hosts:

```bash
pip install -r requirements-ldap.txt
```

VII.5.1 **C2** working defaults (13 groups) live in `c2_groups.py` /
`RoleDefinition.c2_ad_group` (`BB_*`). ДИТ sign-off may replace CNs via JSON.
Plain `ldap://` is rejected unless `AUTH_LDAP_ALLOW_INSECURE_URI=true` (lab).

Ops smoke: [docs/runbooks/i10-ldaps-auth-smoke.md](../../docs/runbooks/i10-ldaps-auth-smoke.md).

### Windows SSO (Kerberos Negotiate)

`AUTH_SSO_NEGOTIATE=true` makes `GET /api/auth/me/` answer `401 WWW-Authenticate: Negotiate`
when the browser has no session. The domain workstation then sends the
Windows ticket. Django checks it with the keytab (`KRB5_KTNAME`) and loads
the person through the existing LDAPS service bind (`LDAPBackend.populate_user`):
`givenName` / `sn`, or `displayName` when those are empty, plus AD groups → I.4 roles.
The user password is not sent again. `POST /api/auth/login/` stays available.

Off by default. A bare IP cannot do this: the site must be opened by the DNS
name registered as `HTTP/<name>` in the bank SPN. The bank also has to mark
that name as intranet in the browser policy, otherwise the ticket is not sent
and `/api/auth/me/` stays 401. Keytab and `krb5.conf` are mounted from
`infra/krb5/` and are not committed.

## RBAC request context

`auth.middleware.RBACMiddleware` runs after Django
`AuthenticationMiddleware` and adds:

- `request.rbac_roles`;
- `request.rbac_permissions`;
- `request.rbac_tabs`.

The same values are available in templates through
`auth.context_processors.rbac`. Tabs not present in `rbac_tabs` must not be
rendered. Backend authorization remains mandatory even when a tab is hidden.

## Decorators

```python
from auth.decorators import admin_permission_required, api_permission_required, panel_tab_required
from auth.roles import PERM_OCR_USE
```

Denied JSON APIs return `401 authentication_required` or
`403 permission_denied`. Django superusers and contractual role 1 have all
Sufler RBAC permissions.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest ..\tests\test_rbac.py ..\tests\test_ldaps_auth.py -q
```
