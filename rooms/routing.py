"""WebSocket URL routes, the Channels equivalent of urls.py."""

from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/rooms/<slug:code>/", consumers.RoomConsumer.as_asgi()),
]
