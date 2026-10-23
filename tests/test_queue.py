"""The story queue, final estimates, and the CSV export."""

import csv
import io
import json

import pytest
from asgiref.sync import sync_to_async
from channels.testing.websocket import WebsocketCommunicator
from django.test import Client
from django.urls import reverse

from config.asgi import application
from rooms import actions, presence
from rooms.decks import FIBONACCI
from rooms.models import Room
from rooms.results import suggest, summarize


@pytest.fixture
def room(db):
    return Room.objects.create()


@pytest.fixture
def ada(room):
    return room.participants.create(display_name="Ada")


def fresh(obj):
    obj.refresh_from_db()
    return obj


def titles(room):
    return list(room.stories.values_list("title", flat=True))


def play_round(room, votes):
    """Everyone votes and the cards are revealed."""
    room = fresh(room)
    for name, card in votes.items():
        player, _ = room.participants.get_or_create(display_name=name)
        actions.vote(room, player, card, room.round)
    actor = room.participants.first()
    actions.reveal(room, actor, room.round)
    return fresh(room)


# --- Adding and arranging


def test_add_stories_one_per_line(room, ada):
    assert actions.add_stories(room, ada, "PROJ-1  Login\n\n  PROJ-2 Logout \r\nPROJ-3 Signup")
    assert titles(room) == ["PROJ-1 Login", "PROJ-2 Logout", "PROJ-3 Signup"]
    assert actions.add_stories(room, ada, "PROJ-4")
    assert titles(room)[-1] == "PROJ-4"


def test_add_stories_ignores_blank_input_and_caps_the_queue(room, ada, monkeypatch):
    assert not actions.add_stories(room, ada, " \n \n")
    monkeypatch.setattr(actions, "MAX_STORIES", 3)
    actions.add_stories(room, ada, "a\nb\nc\nd\ne")
    assert titles(room) == ["a", "b", "c"]
    assert not actions.add_stories(room, ada, "f")


def test_move_story(room, ada):
    actions.add_stories(room, ada, "a\nb\nc")
    b = room.stories.get(title="b")
    assert actions.move_story(room, ada, b.id, "up")
    assert titles(room) == ["b", "a", "c"]
    assert not actions.move_story(room, ada, b.id, "up")  # already first
    assert actions.move_story(room, ada, b.id, "down")
    assert titles(room) == ["a", "b", "c"]


def test_start_story_sets_title_and_fresh_round(room, ada):
    actions.add_stories(room, ada, "a\nb")
    actions.vote(room, ada, "5", 1)
    b = room.stories.get(title="b")
    assert actions.start_story(room, ada, b.id)
    room = fresh(room)
    assert room.current_story == b
    assert room.story_title == "b"
    assert room.round == 2
    assert fresh(ada).vote == ""


def test_renaming_current_story_renames_it_in_queue(room, ada):
    actions.add_stories(room, ada, "Old name")
    actions.start_story(room, ada, room.stories.get().id)
    actions.set_story(fresh(room), ada, "New name")
    assert titles(room) == ["New name"]


def test_queue_respects_facilitator_only(room, ada):
    grace = room.participants.create(display_name="Grace")
    room.facilitator, room.facilitator_only = ada, True
    room.save()
    assert not actions.add_stories(room, grace, "Sneaky")
    assert actions.add_stories(room, ada, "Fine")
    story = room.stories.get()
    assert not actions.start_story(room, grace, story.id)
    assert not actions.remove_story(room, grace, story.id)


# --- Saving estimates


def test_save_estimate_records_votes_and_moves_to_next_story(room, ada):
    actions.add_stories(room, ada, "a\nb")
    actions.start_story(room, ada, room.stories.get(title="a").id)
    room = play_round(room, {"Ada": "5", "Grace": "8"})

    assert actions.save_estimate(room, ada, "8", room.round)
    a = room.stories.get(title="a")
    assert a.estimate == "8"
    assert a.votes == [{"name": "Ada", "vote": "5"}, {"name": "Grace", "vote": "8"}]
    assert a.estimated_at is not None

    room = fresh(room)
    assert room.current_story.title == "b"
    assert room.story_title == "b"
    assert not room.revealed


def test_saving_the_last_story_clears_the_title(room, ada):
    actions.add_stories(room, ada, "only")
    actions.start_story(room, ada, room.stories.get().id)
    room = play_round(room, {"Ada": "3"})
    actions.save_estimate(room, ada, "3", room.round)
    room = fresh(room)
    assert room.current_story is None
    assert room.story_title == ""


def test_saving_without_a_queue_adds_the_round_to_the_list(room, ada):
    actions.set_story(room, ada, "Ad-hoc story")
    room = play_round(room, {"Ada": "2"})
    assert actions.save_estimate(room, ada, "2", room.round)
    story = room.stories.get()
    assert (story.title, story.estimate) == ("Ad-hoc story", "2")


def test_save_estimate_needs_reveal_valid_card_and_current_round(room, ada):
    assert not actions.save_estimate(room, ada, "5", room.round)  # not revealed
    room = play_round(room, {"Ada": "5"})
    assert not actions.save_estimate(room, ada, "40", room.round)  # not in deck
    assert not actions.save_estimate(room, ada, "5", room.round - 1)  # stale
    assert actions.save_estimate(room, ada, "5", room.round)
    assert not actions.save_estimate(fresh(room), ada, "5", room.round)  # double click


# --- Suggested estimate


@pytest.mark.parametrize(
    ("votes", "expected"),
    [
        (["5", "5", "?"], "5"),  # consensus
        (["3", "5", "8"], "5"),  # average 5.3, nearest 5
        (["5", "8"], "8"),  # average 6.5: tie between 5 and 8, pick the higher
        (["1", "2"], "2"),  # average 1.5: tie, higher
        (["13", "13", "8"], "13"),  # average 11.3, nearest 13
    ],
)
def test_suggest_numeric(votes, expected):
    assert suggest(summarize(votes, FIBONACCI), FIBONACCI) == expected


def test_suggest_non_numeric():
    tshirt = ["XS", "S", "M", "L", "XL", "?", "☕"]
    assert suggest(summarize(["M", "L", "L"], tshirt), tshirt) == "L"


# --- CSV export


def join(client, room, name="Viewer"):
    client.post(reverse("rooms:join", kwargs={"code": room.code}), {"display_name": name})


def read_csv(response):
    text = response.content.decode("utf-8-sig")  # strips the Excel byte-order mark
    return list(csv.reader(io.StringIO(text)))


def test_csv_lists_stories_estimates_and_votes(client, room, ada):
    room.deck = ["½", "1", "2", "3", "5", "8"]  # ½ checks that non-ASCII survives
    room.save()
    join(client, room)
    actions.add_stories(room, ada, "Login\nLogout")
    actions.start_story(room, ada, room.stories.get(title="Login").id)
    room = play_round(room, {"Ada": "5", "Grace": "½"})
    actions.save_estimate(room, ada, "5", room.round)

    response = client.get(reverse("rooms:export", kwargs={"code": room.code}))
    assert response["Content-Type"].startswith("text/csv")
    assert f"story-points-{room.code}-" in response["Content-Disposition"]
    rows = read_csv(response)
    assert rows[0] == ["Story", "Estimate", "Votes", "Estimated at (UTC)"]
    assert rows[1][:3] == ["Login", "5", "Ada: 5; Grace: ½"]
    assert rows[1][3]  # a timestamp
    assert rows[2] == ["Logout", "", "", ""]  # still waiting


def test_csv_neutralises_spreadsheet_formulas(client, room, ada):
    join(client, room)
    actions.add_stories(room, ada, '=HYPERLINK("http://evil.example")\n+1\nNormal')
    rows = read_csv(client.get(reverse("rooms:export", kwargs={"code": room.code})))
    assert [row[0] for row in rows[1:]] == ['\'=HYPERLINK("http://evil.example")', "'+1", "Normal"]


def test_csv_is_only_for_people_in_the_room(room):
    response = Client().get(reverse("rooms:export", kwargs={"code": room.code}))
    assert response.status_code == 302
    assert response.url == reverse("rooms:join", kwargs={"code": room.code})


# --- Live


@pytest.mark.django_db(transaction=True)
async def test_queue_flow_over_websocket():
    presence.reset()
    room = await sync_to_async(Room.objects.create)()

    @sync_to_async
    def session():
        client = Client()
        join(client, room)
        return client.cookies["sessionid"].value

    ws = WebsocketCommunicator(
        application,
        f"/ws/rooms/{room.code}/",
        headers=[(b"origin", b"http://localhost"), (b"cookie", f"sessionid={await session()}".encode())],
    )
    await ws.connect()

    async def send(**message):
        await ws.send_to(text_data=json.dumps(message))
        html = None
        while not await ws.receive_nothing(timeout=0.2):
            html = await ws.receive_from()
        return html

    await send()  # drain the connect update
    view = await send(action="add_stories", stories="PROJ-1 Login\nPROJ-2 Logout")
    assert "PROJ-1 Login" in view and "Estimate now" in view

    story_id = await sync_to_async(lambda: room.stories.get(title="PROJ-1 Login").id)()
    view = await send(action="start_story", target=str(story_id))
    assert "<h1>PROJ-1 Login</h1>" in view

    await send(action="vote", round="2", value="8")
    view = await send(action="reveal", round="2")
    assert '<option value="8" selected>' in view
    assert "Save &amp; next story" in view

    view = await send(action="save_estimate", round="2", estimate="8")
    assert "<h1>PROJ-2 Logout</h1>" in view
    assert "1 of 2 estimated" in view
    await ws.disconnect()
    presence.reset()
