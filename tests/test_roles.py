"""Facilitator and observer roles."""

import json
import re

import pytest
from asgiref.sync import sync_to_async
from channels.testing.websocket import WebsocketCommunicator
from django.test import Client
from django.urls import reverse

from config.asgi import application
from rooms import actions, presence
from rooms.models import Room

# --- Permissions (no WebSockets)


@pytest.fixture
def room(db):
    return Room.objects.create()


@pytest.fixture
def ada(room):
    """The facilitator."""
    ada = room.participants.create(display_name="Ada")
    room.facilitator = ada
    room.save()
    return ada


@pytest.fixture
def grace(room):
    return room.participants.create(display_name="Grace")


def fresh(obj):
    obj.refresh_from_db()
    return obj


def test_anyone_controls_by_default(room, ada, grace):
    assert actions.reveal(room, grace, 1)


def test_facilitator_only_room_blocks_everyone_else(room, ada, grace):
    room.facilitator_only = True
    room.save()
    assert not actions.reveal(room, grace, 1)
    assert not actions.next_round(room, grace, 1)
    assert not actions.set_story(room, grace, "Sneaky")
    assert not actions.set_deck(room, grace, ["S", "M"])
    assert actions.reveal(room, ada, 1)


def test_only_facilitator_changes_the_setting(room, ada, grace):
    assert not actions.set_facilitator_only(room, grace, True)
    assert actions.set_facilitator_only(room, ada, True)
    assert fresh(room).facilitator_only


def test_observers_cannot_vote(room, grace):
    grace.is_observer = True
    grace.save()
    assert not actions.vote(room, grace, "5", 1)


def test_switching_to_observer_withdraws_vote(room, grace):
    actions.vote(room, grace, "5", 1)
    assert actions.set_observing(room, grace, grace.id, True)
    grace = fresh(grace)
    assert grace.is_observer
    assert grace.vote == ""


def test_only_facilitator_switches_other_people(room, ada, grace):
    assert not actions.set_observing(room, grace, ada.id, True)
    assert actions.set_observing(room, ada, grace.id, True)
    assert fresh(grace).is_observer


def test_hand_over(room, ada, grace):
    assert not actions.hand_over(room, grace, grace.id)  # not the facilitator
    assert actions.hand_over(room, ada, grace.id)
    assert fresh(room).facilitator == grace


def test_take_over_only_when_facilitator_is_away(room, ada, grace):
    assert not actions.take_over(room, grace, online_ids={ada.id, grace.id})
    assert actions.take_over(room, grace, online_ids={grace.id})
    assert fresh(room).facilitator == grace


def test_take_over_when_there_is_no_facilitator(room, grace):
    assert actions.take_over(room, grace, online_ids={grace.id})


def test_remove_player(room, ada, grace):
    assert not actions.remove_player(room, grace, ada.id)  # not the facilitator
    assert not actions.remove_player(room, ada, ada.id)  # not yourself
    assert actions.remove_player(room, ada, grace.id)
    assert list(room.participants.all()) == [ada]


# --- Creating and joining


@pytest.mark.django_db
def test_creator_becomes_facilitator_others_do_not(client):
    client.post(reverse("rooms:create"), {"deck": "fibonacci", "control": "facilitator"})
    room = Room.objects.get()
    assert room.facilitator_only
    join_url = reverse("rooms:join", kwargs={"code": room.code})

    Client().post(join_url, {"display_name": "Grace"})  # someone else joins first
    client.post(join_url, {"display_name": "Ada"})
    assert fresh(room).facilitator.display_name == "Ada"


@pytest.mark.django_db
def test_rooms_default_to_anyone_controls(client):
    client.post(reverse("rooms:create"), {"deck": "fibonacci"})
    assert not Room.objects.get().facilitator_only


def test_join_as_observer(room):
    Client().post(reverse("rooms:join", kwargs={"code": room.code}), {"display_name": "Pat", "observer": "on"})
    assert room.participants.get().is_observer


# --- Live behaviour


@pytest.fixture
def clear_presence():
    presence.reset()
    yield
    presence.reset()


@sync_to_async
def make_room(**fields):
    return Room.objects.create(**fields)


@sync_to_async
def join_as(room, name, *, facilitator=False, observer=False):
    client = Client()
    client.post(reverse("rooms:join", kwargs={"code": room.code}), {"display_name": name, "observer": observer})
    if facilitator:
        room.facilitator = room.participants.get(display_name=name)
        room.save(update_fields=["facilitator"])
    return client.cookies["sessionid"].value, room.participants.get(display_name=name).id


async def connect(room, session_id):
    ws = WebsocketCommunicator(
        application,
        f"/ws/rooms/{room.code}/",
        headers=[(b"origin", b"http://localhost"), (b"cookie", f"sessionid={session_id}".encode())],
    )
    assert (await ws.connect())[0]
    return ws


async def drain(*sockets):
    """Read every pending update; return the last one for each socket."""
    last = []
    for ws in sockets:
        html = None
        while not await ws.receive_nothing(timeout=0.2):
            html = await ws.receive_from()
        last.append(html)
    return last


async def send(ws, **message):
    await ws.send_to(text_data=json.dumps(message))


@pytest.mark.django_db(transaction=True)
async def test_facilitator_only_room_shows_buttons_only_to_facilitator(clear_presence):
    room = await make_room(facilitator_only=True)
    ada_session, _ = await join_as(room, "Ada", facilitator=True)
    grace_session, _ = await join_as(room, "Grace")
    ada, grace = await connect(room, ada_session), await connect(room, grace_session)
    ada_view, grace_view = await drain(ada, grace)

    assert "Reveal cards" in ada_view
    assert "Reveal cards" not in grace_view
    assert "Waiting for Ada to reveal" in grace_view
    assert 'data-locked="true"' in grace_view
    assert 'data-locked="false"' in ada_view

    await send(grace, action="reveal", round="1")  # ignored
    assert await grace.receive_nothing()
    await ada.disconnect()
    await grace.disconnect()


@pytest.mark.django_db(transaction=True)
async def test_observers_are_not_counted_and_get_no_cards(clear_presence):
    room = await make_room()
    ada_session, _ = await join_as(room, "Ada")
    pat_session, _ = await join_as(room, "Pat", observer=True)
    ada, pat = await connect(room, ada_session), await connect(room, pat_session)
    ada_view, pat_view = await drain(ada, pat)

    assert "0 of 1 voted" in ada_view
    assert "Observer" in ada_view
    assert "You're observing" in pat_view
    assert 'name="action" value="vote"' not in pat_view
    await ada.disconnect()
    await pat.disconnect()


@pytest.mark.django_db(transaction=True)
async def test_removed_player_is_told_and_disconnected(clear_presence):
    room = await make_room()
    ada_session, _ = await join_as(room, "Ada", facilitator=True)
    grace_session, grace_id = await join_as(room, "Grace")
    ada, grace = await connect(room, ada_session), await connect(room, grace_session)
    await drain(ada, grace)

    await send(ada, action="remove", target=str(grace_id))
    notice = await grace.receive_from()
    assert "removed you" in notice
    assert await grace.receive_output() == {"type": "websocket.close", "code": 4403}

    (ada_view,) = await drain(ada)
    players = re.search(r'<section id="participants".*?</section>', ada_view, re.S).group(0)
    assert "Grace" not in players
    await ada.disconnect()


@pytest.mark.django_db(transaction=True)
async def test_anyone_can_take_over_when_facilitator_leaves(clear_presence):
    room = await make_room(facilitator_only=True)
    ada_session, _ = await join_as(room, "Ada", facilitator=True)
    grace_session, grace_id = await join_as(room, "Grace")
    ada, grace = await connect(room, ada_session), await connect(room, grace_session)
    _, grace_view = await drain(ada, grace)
    assert "Become facilitator" not in grace_view

    await ada.disconnect()
    (grace_view,) = await drain(grace)
    assert "Ada (offline)" in grace_view
    assert "Become facilitator" in grace_view

    await send(grace, action="take_over")
    (grace_view,) = await drain(grace)
    assert "Reveal cards" in grace_view
    assert (await sync_to_async(lambda: Room.objects.get(id=room.id).facilitator_id)()) == grace_id
    await grace.disconnect()
