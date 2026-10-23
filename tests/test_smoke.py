from channels.testing.websocket import WebsocketCommunicator

from config.asgi import application


def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Story Point Poker" in response.content


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.content == b"ok"


async def test_websocket_from_another_site_is_rejected():
    communicator = WebsocketCommunicator(application, "/ws/rooms/abc/", headers=[(b"origin", b"https://evil.example")])
    connected, _ = await communicator.connect()
    assert not connected
