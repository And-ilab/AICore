from django.urls import re_path

from telephony.consumers import SuflerTranscriptConsumer

websocket_urlpatterns = [
    re_path(
        r"^ws/sufler/(?P<call_id>[\w-]+)/$",
        SuflerTranscriptConsumer.as_asgi(),
    ),
    re_path(
        r"^ws/sufler/$",
        SuflerTranscriptConsumer.as_asgi(),
    ),
]
