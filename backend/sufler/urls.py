from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from core.health import health
from core.metrics import metrics

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("metrics/", metrics, name="metrics"),
    path("api/admin/", include("hub.urls")),
    path("api/reports/", include("reports.urls")),
    path("api/auth/", include("auth.urls")),
    path("api/v1/knowledge/", include("ingest.urls")),
    path("api/v1/sufler/", include("orchestrator.urls")),
    path("api/v1/assistant/", include("assistant.urls")),
    path("api/v1/ocr/", include("ocr.urls")),
    path("api/v1/channels/", include("integrations.channels.urls")),
    path("api/v1/telephony/oktell/", include("integrations.oktell.urls")),
    path("api/v1/online-chat/", include("online_chat.urls")),
    path(
        "api/schema/",
        SpectacularAPIView.as_view(),
        name="schema",
    ),
    path("", include("chat.urls")),
]

# Swagger / ReDoc — development only.
if settings.DEBUG:
    urlpatterns += [
        path(
            "api/docs/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
        path(
            "api/redoc/",
            SpectacularRedocView.as_view(url_name="schema"),
            name="redoc",
        ),
    ]
