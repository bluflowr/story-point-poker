import pytest
from django.test import Client
from django.urls import reverse

from rooms.decks import FIBONACCI
from rooms.models import ROOM_CODE_ALPHABET, ROOM_CODE_LENGTH, Participant, Room

pytestmark = pytest.mark.django_db


def create_room(client):
    response = client.post(reverse("rooms:create"))
    return Room.objects.get(), response


def join(client, room, name="Ada"):
    return client.post(reverse("rooms:join", kwargs={"code": room.code}), {"display_name": name})


def test_new_room_gets_random_readable_code_and_default_deck():
    room = Room.objects.create()
    assert len(room.code) == ROOM_CODE_LENGTH
    assert set(room.code) <= set(ROOM_CODE_ALPHABET)
    assert room.deck == FIBONACCI
    assert Room.objects.create().code != room.code


def test_create_room_requires_post(client):
    assert client.get(reverse("rooms:create")).status_code == 405
    assert not Room.objects.exists()


def test_create_room_redirects_to_room(client):
    room, response = create_room(client)
    assert response.status_code == 302
    assert response.url == room.get_absolute_url()


def test_visiting_room_before_joining_redirects_to_join(client):
    room, _ = create_room(client)
    response = client.get(room.get_absolute_url())
    assert response.status_code == 302
    assert response.url == reverse("rooms:join", kwargs={"code": room.code})


def test_join_creates_participant_and_shows_room(client):
    room, _ = create_room(client)
    response = join(client, room, "Ada")
    assert response.status_code == 302
    assert response.url == room.get_absolute_url()

    participant = Participant.objects.get()
    assert participant.room == room
    assert participant.display_name == "Ada"

    page = client.get(room.get_absolute_url())
    assert page.status_code == 200
    assert b"Ada" in page.content
    assert room.code.encode() in page.content  # share link


def test_refresh_keeps_seat_and_join_page_bounces_back(client):
    room, _ = create_room(client)
    join(client, room)
    assert client.get(room.get_absolute_url()).status_code == 200
    response = client.get(reverse("rooms:join", kwargs={"code": room.code}))
    assert response.status_code == 302
    assert response.url == room.get_absolute_url()
    assert Participant.objects.count() == 1


def test_room_lists_everyone_who_joined(client):
    room, _ = create_room(client)
    join(client, room, "Ada")
    other = Client()
    join(other, room, "Grace")

    page = other.get(room.get_absolute_url()).content.decode()
    assert "Ada" in page
    assert "Grace" in page
    assert Participant.objects.filter(room=room).count() == 2


@pytest.mark.parametrize("name", ["", "   ", "x" * 31])
def test_join_rejects_invalid_names(client, name):
    room, _ = create_room(client)
    response = join(client, room, name)
    assert response.status_code == 200
    assert not Participant.objects.exists()


def test_join_strips_whitespace(client):
    room, _ = create_room(client)
    join(client, room, "  Ada  ")
    assert Participant.objects.get().display_name == "Ada"


def test_name_is_prefilled_in_the_next_room(client):
    first, _ = create_room(client)
    join(client, first, "Ada")
    second = Room.objects.create()
    page = client.get(reverse("rooms:join", kwargs={"code": second.code}))
    assert b'value="Ada"' in page.content


def test_joining_marks_room_active(client):
    room, _ = create_room(client)
    before = room.last_activity_at
    join(client, room)
    room.refresh_from_db()
    assert room.last_activity_at > before


def test_unknown_room_is_404(client):
    assert client.get("/r/doesnotexist/").status_code == 404
    assert client.get("/r/doesnotexist/join").status_code == 404
