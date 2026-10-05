"""VI.3 audit taxonomy and event type constants."""

from __future__ import annotations


CATEGORY_AUTHENTICATION = "authentication"
CATEGORY_AUTHORIZATION = "authorization"
CATEGORY_ADMINISTRATION = "administration"
CATEGORY_DATA_SECURITY = "data_security"
CATEGORY_INTEGRATIONS = "integrations"

AUDIT_CATEGORIES = frozenset(
    {
        CATEGORY_AUTHENTICATION,
        CATEGORY_AUTHORIZATION,
        CATEGORY_ADMINISTRATION,
        CATEGORY_DATA_SECURITY,
        CATEGORY_INTEGRATIONS,
    }
)

RESULT_SUCCESS = "success"
RESULT_FAILURE = "failure"
RESULT_UNKNOWN = "unknown"
AUDIT_RESULTS = frozenset(
    {RESULT_SUCCESS, RESULT_FAILURE, RESULT_UNKNOWN}
)

LOGIN_SUCCESS = "hub.authentication.login_success"
LOGIN_FAILURE = "hub.authentication.login_failure"
LOGOUT = "hub.authentication.logout"
ACCESS_DENIED = "hub.authorization.access_denied"
KB_SETTINGS_UPDATED = "hub.administration.kb_settings_updated"
WEBSITE_CRAWL_IGNORE_ROBOTS = "hub.administration.website_crawl_ignore_robots"
AUDIT_WRITE_FAILURE = "hub.data.audit_write_failure"
SIEM_DELIVERY_FAILURE = "hub.integrations.siem_delivery_failure"
ASSISTANT_SANDBOX_SNIPPET = "hub.data_security.assistant_sandbox_snippet"
ONLINE_CHAT_CLIENT_BLOCKED = "hub.online_chat.client_blocked"
ONLINE_CHAT_CLIENT_UNBLOCKED = "hub.online_chat.client_unblocked"
