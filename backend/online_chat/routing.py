from django.urls import re_path

from online_chat.consumers import OnlineChatArmConsumer, OnlineChatDialogConsumer

websocket_urlpatterns = [
    re_path(r"^ws/online-chat/arm/$", OnlineChatArmConsumer.as_asgi()),
    re_path(
        r"^ws/online-chat/dialog/(?P<dialog_id>[0-9a-f-]+)/$",
        OnlineChatDialogConsumer.as_asgi(),
    ),
]
