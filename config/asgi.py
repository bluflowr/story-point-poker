"""
ASGI entry point. Uvicorn runs `config.asgi:application`.

Normal HTTP requests go to Django's views. WebSocket connections are routed
to Channels consumers; the room consumer gets added here in milestone 2.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Set up Django before importing anything that touches models.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
from channels.sessions import SessionMiddlewareStack  # noqa: E402

from rooms.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # Rejects WebSocket connections from pages on other sites, and
        # gives consumers access to the visitor's Django session.
        "websocket": AllowedHostsOriginValidator(SessionMiddlewareStack(URLRouter(websocket_urlpatterns))),
    }
)
