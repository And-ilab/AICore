from django.urls import path

from integrations.oktell.views import (
    oktell_call_detail,
    oktell_call_started,
    oktell_call_stopped,
    oktell_calls,
    oktell_listen_now,
)

urlpatterns = [
    path("call-started", oktell_call_started, name="oktell_call_started"),
    path("call-stopped", oktell_call_stopped, name="oktell_call_stopped"),
    path("listen-now", oktell_listen_now, name="oktell_listen_now"),
    path("calls", oktell_calls, name="oktell_calls"),
    path("calls/<str:idchain>", oktell_call_detail, name="oktell_call_detail"),
]
