import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

django_asgi_app = get_asgi_application()

from online_chat.routing import websocket_urlpatterns as online_chat_ws  # noqa: E402
from telephony.routing import websocket_urlpatterns as telephony_ws  # noqa: E402

websocket_urlpatterns = [
    *telephony_ws,
    *online_chat_ws,
]

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
