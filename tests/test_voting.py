"""The voting loop over real WebSocket connections."""

import json
import re

import pytest
from asgiref.sync import sync_to_async
from channels.testing.websocket import WebsocketCommunicator
from django.test import Client
from django.urls import reverse

from config.asgi import application
from rooms import presence
from rooms.models import Room

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
    client = Client()
    client.post(reverse("rooms:join", kwargs={"code": room.code}), {"display_name": name})
    return client.cookies["sessionid"].value


class Player:
    """One browser in the room."""

    def __init__(self, room, session_id):
        self.room = room
        self.ws = WebsocketCommunicator(
            application,
            f"/ws/rooms/{room.code}/",
            headers=[(b"origin", b"http://localhost"), (b"cookie", f"sessionid={session_id}".encode())],
        )

    async def send(self, **message):
        await self.ws.send_to(text_data=json.dumps(message))

    async def latest(self):
        """Wait for the next pushed update and return it."""
        return await self.ws.receive_from()


async def seat(room, *names):
    """Join and connect each player, draining the connect broadcasts."""
    players = []
    for name in names:
        player = Player(room, await join_as(room, name))
        connected, _ = await player.ws.connect()
        assert connected
        players.append(player)
        for p in players:
            await p.latest()
    return players


async def leave(*players):
    for p in players:
        await p.ws.disconnect()


def player_list(html):
    return re.search(r'<section id="participants".*?</section>', html, re.S).group(0)


def card_in_row(html, name):
    """The mini-card shown next to a player's name."""
    row = re.search(rf"{name}.*?<span class=\"mini-card[^\"]*\"[^>]*>([^<]*)</span>", html, re.S)
    return row.group(1).strip()


async def test_others_see_that_you_voted_but_not_what():
    room = await new_room()
    ada, grace = await seat(room, "Ada", "Grace")

    await ada.send(action="vote", round="1", value="8")
    ada_view, grace_view = await ada.latest(), await grace.latest()

    assert card_in_row(grace_view, "Ada") == "✓"
    assert "8" not in player_list(grace_view)
    assert "1 of 2 voted" in grace_view
    assert 'class="card selected"' in ada_view
    assert 'class="card selected"' not in grace_view
    await leave(ada, grace)


async def test_reveal_shows_everyones_cards_and_results():
    room = await new_room()
    ada, grace = await seat(room, "Ada", "Grace")
    for player, card in ((ada, "5"), (grace, "8")):
        await player.send(action="vote", round="1", value=card)
        await ada.latest(), await grace.latest()

    await grace.send(action="reveal", round="1")
    view = await ada.latest()
    await grace.latest()

    assert card_in_row(view, "Ada") == "5"
    assert card_in_row(view, "Grace") == "8"
    assert "Average" in view and "6.5" in view
    assert "Next round" in view
    await leave(ada, grace)


async def test_consensus_is_highlighted():
    room = await new_room()
    ada, grace = await seat(room, "Ada", "Grace")
    for player in (ada, grace):
        await player.send(action="vote", round="1", value="3")
        await ada.latest(), await grace.latest()
    await ada.send(action="reveal", round="1")
    assert "Everyone agrees" in await ada.latest()
    await grace.latest()
    await leave(ada, grace)


async def test_next_round_resets_the_board():
    room = await new_room()
    (ada,) = await seat(room, "Ada")
    await ada.send(action="vote", round="1", value="5")
    await ada.latest()
    await ada.send(action="reveal", round="1")
    await ada.latest()

    await ada.send(action="next_round", round="1")
    view = await ada.latest()
    assert "Round 2" in view
    assert "0 of 1 voted" in view
    assert 'class="card selected"' not in view
    assert 'name="round" value="2"' in view
    await leave(ada)


async def test_story_title_is_shared():
    room = await new_room()
    ada, grace = await seat(room, "Ada", "Grace")
    await ada.send(action="story", title="PROJ-42 Export to CSV", HEADERS={"HX-Request": "true"})
    await ada.latest()
    assert "PROJ-42 Export to CSV" in await grace.latest()
    await leave(ada, grace)


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[1, 2]",
        json.dumps({"action": "vote", "round": "1", "value": "999"}),
        json.dumps({"action": "vote", "round": "abc", "value": "5"}),
        json.dumps({"action": "explode"}),
    ],
)
async def test_bad_messages_are_ignored(raw):
    room = await new_room()
    (ada,) = await seat(room, "Ada")
    await ada.ws.send_to(text_data=raw)
    assert await ada.ws.receive_nothing()
    await leave(ada)


async def test_switching_deck_updates_everyones_cards():
    room = await new_room()
    ada, grace = await seat(room, "Ada", "Grace")
    await ada.send(action="vote", round="1", value="5")
    await ada.latest(), await grace.latest()

    await grace.send(action="deck", deck="tshirt", custom="")
    view = await ada.latest()
    await grace.latest()
    assert 'name="value" value="XL"' in view
    assert 'name="value" value="13"' not in view
    assert "Round 2" in view
    assert "0 of 2 voted" in view
    await leave(ada, grace)


async def test_bad_custom_deck_error_goes_only_to_sender():
    room = await new_room()
    ada, grace = await seat(room, "Ada", "Grace")

    await ada.send(action="deck", deck="custom", custom="WAYTOOLONG, 1")
    error = await ada.latest()
    assert 'id="deck-error"' in error
    assert "at most 4 characters" in error
    assert await grace.ws.receive_nothing()
    await leave(ada, grace)


async def test_message_flood_is_dropped(monkeypatch):
    from rooms.consumers import RoomConsumer

    monkeypatch.setattr(RoomConsumer, "message_limit", 2)
    room = await new_room()
    (ada,) = await seat(room, "Ada")
    for title in ("one", "two"):
        await ada.send(action="story", title=title)
        await ada.latest()
    await ada.send(action="story", title="three")
    assert await ada.ws.receive_nothing()
    await leave(ada)


async def test_oversized_message_is_ignored():
    room = await new_room()
    (ada,) = await seat(room, "Ada")
    await ada.send(action="story", title="x" * 5000)
    assert await ada.ws.receive_nothing()
    await leave(ada)


async def test_keepalive_ping_changes_nothing():
    room = await new_room()
    (ada,) = await seat(room, "Ada")
    await ada.send(action="ping")
    assert await ada.ws.receive_nothing()
    await leave(ada)
