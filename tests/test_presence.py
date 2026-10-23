import pytest
from asgiref.sync import sync_to_async
from channels.testing.websocket import WebsocketCommunicator
from django.test import Client
from django.urls import reverse

from config.asgi import application
from rooms import presence
from rooms.models import Room

# Consumers touch the database from another thread, which needs real transactions.
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def clear_presence():
    presence.reset()
    yield
    presence.reset()


@sync_to_async
def new_room():
    return Room.objects.create()


@sync_to_async
def join_as(room, name):
    """Join through the real page, like a browser would. Returns the session id."""
    client = Client()
    client.post(reverse("rooms:join", kwargs={"code": room.code}), {"display_name": name})
    return client.cookies["sessionid"].value


def socket(room_code, session_id=None):
    headers = [(b"origin", b"http://localhost")]
    if session_id:
        headers.append((b"cookie", f"sessionid={session_id}".encode()))
    return WebsocketCommunicator(application, f"/ws/rooms/{room_code}/", headers=headers)


async def test_member_connects_and_gets_player_list():
    room = await new_room()
    ada = socket(room.code, await join_as(room, "Ada"))

    connected, _ = await ada.connect()
    assert connected

    html = await ada.receive_from()
    assert 'id="participants"' in html
    assert "Ada" in html
    assert "(you)" in html
    assert "1 online" in html
    await ada.disconnect()


async def assert_turned_away(ws, close_code, text):
    """The server accepts, sends a notice, then closes so the browser stops retrying."""
    connected, _ = await ws.connect()
    assert connected
    notice = await ws.receive_from()
    assert 'id="notice"' in notice
    assert text in notice
    assert await ws.receive_output() == {"type": "websocket.close", "code": close_code}


async def test_visitor_who_has_not_joined_is_told_to_join():
    room = await new_room()
    await assert_turned_away(socket(room.code), 4403, "Join again")


async def test_member_of_another_room_is_told_to_join():
    room, other_room = await new_room(), await new_room()
    session = await join_as(room, "Ada")
    await assert_turned_away(socket(other_room.code, session), 4403, "Join again")


async def test_unknown_room_says_it_has_expired():
    await assert_turned_away(socket("doesnotexist"), 4404, "expired")


async def test_turned_away_visitor_is_not_counted_online():
    room = await new_room()
    await assert_turned_away(socket(room.code), 4403, "Join again")
    assert presence.online_ids(room.code) == set()


async def test_everyone_sees_players_come_online_and_go_offline():
    room = await new_room()
    ada = socket(room.code, await join_as(room, "Ada"))
    grace = socket(room.code, await join_as(room, "Grace"))

    await ada.connect()
    await ada.receive_from()

    await grace.connect()
    html = await ada.receive_from()
    assert "2 online" in html
    assert "Grace" in html
    assert (await grace.receive_from()).count("(you)") == 1

    await grace.disconnect()
    html = await ada.receive_from()
    assert "1 online" in html
    assert 'class="offline"' in html  # Grace stays in the list, greyed out
    await ada.disconnect()


async def test_closing_one_of_two_tabs_keeps_player_online():
    room = await new_room()
    session = await join_as(room, "Ada")
    tab1, tab2 = socket(room.code, session), socket(room.code, session)

    await tab1.connect()
    await tab1.receive_from()
    await tab2.connect()
    await tab1.receive_from()
    await tab2.receive_from()

    await tab2.disconnect()
    html = await tab1.receive_from()
    assert "1 online" in html
    assert 'class="offline"' not in html
    await tab1.disconnect()
    assert presence.online_ids(room.code) == set()


def test_presence_counts_connections_per_participant():
    presence.connect("room1", 7)
    presence.connect("room1", 7)
    presence.connect("room1", 8)
    presence.disconnect("room1", 7)
    assert presence.online_ids("room1") == {7, 8}
    presence.disconnect("room1", 7)
    presence.disconnect("room1", 8)
    assert presence.online_ids("room1") == set()
    assert presence.online_ids("never-used") == set()
