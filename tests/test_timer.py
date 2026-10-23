"""The round timer."""

import json
from datetime import timedelta

import pytest
from asgiref.sync import sync_to_async
from channels.testing.websocket import WebsocketCommunicator
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from config.asgi import application
from rooms import actions, presence
from rooms.models import Room
from rooms.templatetags.rooms import minutes_seconds


@pytest.fixture
def room(db):
    return Room.objects.create()


@pytest.fixture
def ada(room):
    return room.participants.create(display_name="Ada")


def fresh(obj):
    obj.refresh_from_db()
    return obj


def test_start_timer_sets_end_time(room, ada):
    before = timezone.now()
    assert actions.start_timer(room, ada, 60)
    ends = fresh(room).timer_ends_at
    assert before + timedelta(seconds=59) < ends <= timezone.now() + timedelta(seconds=60)


def test_only_preset_lengths(room, ada):
    assert not actions.start_timer(room, ada, 45)
    assert not actions.start_timer(room, ada, None)
    assert fresh(room).timer_ends_at is None


def test_facilitator_only_room_limits_timer(room, ada):
    grace = room.participants.create(display_name="Grace")
    room.facilitator, room.facilitator_only = ada, True
    room.save()
    assert not actions.start_timer(room, grace, 60)
    assert actions.start_timer(room, ada, 60)
    assert not actions.stop_timer(fresh(room), grace)
    assert actions.stop_timer(fresh(room), ada)


def test_no_timer_once_revealed(room, ada):
    actions.reveal(room, ada, 1)
    assert not actions.start_timer(fresh(room), ada, 60)


@pytest.mark.parametrize("finish", ["reveal", "next_round"])
def test_reveal_and_next_round_clear_timer(room, ada, finish):
    actions.start_timer(room, ada, 60)
    getattr(actions, finish)(fresh(room), ada, 1)
    assert fresh(room).timer_ends_at is None


def test_switching_deck_clears_timer(room, ada):
    actions.start_timer(room, ada, 60)
    actions.set_deck(fresh(room), ada, ["S", "M"])
    assert fresh(room).timer_ends_at is None


def test_seconds_left(room):
    now = timezone.now()
    assert actions.timer_seconds_left(room, now) is None
    room.timer_ends_at = now + timedelta(seconds=30, milliseconds=200)
    assert actions.timer_seconds_left(room, now) == 31  # rounds up, so it never shows 0 early
    room.timer_ends_at = now - timedelta(seconds=5)
    assert actions.timer_seconds_left(room, now) == 0


def test_minutes_seconds_filter():
    assert minutes_seconds(125) == "2:05"
    assert minutes_seconds(30) == "0:30"


# --- Live


@sync_to_async
def join_as(room, name):
    client = Client()
    client.post(reverse("rooms:join", kwargs={"code": room.code}), {"display_name": name})
    return client.cookies["sessionid"].value


async def connect(room, session_id):
    ws = WebsocketCommunicator(
        application,
        f"/ws/rooms/{room.code}/",
        headers=[(b"origin", b"http://localhost"), (b"cookie", f"sessionid={session_id}".encode())],
    )
    assert (await ws.connect())[0]
    return ws


async def latest(ws):
    html = None
    while not await ws.receive_nothing(timeout=0.2):
        html = await ws.receive_from()
    return html


@pytest.mark.django_db(transaction=True)
async def test_timer_is_shared_with_everyone():
    presence.reset()
    room = await sync_to_async(Room.objects.create)()
    ada = await connect(room, await join_as(room, "Ada"))
    grace = await connect(room, await join_as(room, "Grace"))
    await latest(ada)
    assert 'name="action" value="start_timer"' in await latest(grace)

    await ada.send_to(text_data=json.dumps({"action": "start_timer", "seconds": "120"}))
    view = await latest(grace)
    assert 'data-seconds-left="120"' in view or 'data-seconds-left="119"' in view
    assert "2:00" in view or "1:59" in view
    assert "Stop timer" in view

    await grace.send_to(text_data=json.dumps({"action": "stop_timer"}))
    assert "data-seconds-left" not in await latest(ada)
    await ada.disconnect()
    await grace.disconnect()
    presence.reset()
