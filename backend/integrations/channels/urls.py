from django.urls import path

from integrations.channels.webhooks import (
    api_webhook,
    channel_inbox,
    ok_webhook,
    telegram_webhook,
    viber_webhook,
    vk_webhook,
    widget_message,
)

urlpatterns = [
    path(
        "telegram/webhook/",
        telegram_webhook,
        name="telegram_webhook",
    ),
    path(
        "viber/webhook/",
        viber_webhook,
        name="viber_webhook",
    ),
    path("vk/webhook/", vk_webhook, name="vk_webhook"),
    path("ok/webhook/", ok_webhook, name="ok_webhook"),
    path("api/webhook/", api_webhook, name="api_channel_webhook"),
    path(
        "widget/<str:widget_id>/messages/",
        widget_message,
        name="widget_message",
    ),
    path("inbox/", channel_inbox, name="channel_inbox"),
]
