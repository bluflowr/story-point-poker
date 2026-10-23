from datetime import timedelta

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from rooms import presence, views
from rooms.expiry import delete_expired_rooms
from rooms.limits import RateLimiter, client_ip
from rooms.models import Room

# --- Rate limiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_limiter_allows_up_to_limit_then_refuses():
    limiter = RateLimiter(limit=3, window=60, clock=FakeClock())
    assert [limiter.allow("a") for _ in range(4)] == [True, True, True, False]
    assert limiter.allow("b")  # other keys are separate


def test_limiter_frees_up_as_the_window_moves_on():
    clock = FakeClock()
    limiter = RateLimiter(limit=1, window=60, clock=clock)
    assert limiter.allow()
    assert not limiter.allow()
    clock.now += 61
    assert limiter.allow()


def test_client_ip_prefers_first_forwarded_address(rf):
    request = rf.get("/", HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1", REMOTE_ADDR="10.0.0.2")
    assert client_ip(request) == "203.0.113.7"
    assert client_ip(rf.get("/", REMOTE_ADDR="10.0.0.2")) == "10.0.0.2"


# --- Room creation limits


def create(client, ip):
    return client.post(reverse("rooms:create"), {"deck": "fibonacci"}, HTTP_X_FORWARDED_FOR=ip)


@pytest.mark.django_db
def test_room_creation_is_limited_per_ip(client):
    for _ in range(views.ROOM_CREATION_PER_IP.limit):
        assert create(client, "203.0.113.7").status_code == 302
    response = create(client, "203.0.113.7")
    assert response.status_code == 429
    assert b"Too many new rooms" in response.content
    assert create(client, "198.51.100.1").status_code == 302


@pytest.mark.django_db
def test_room_creation_has_an_overall_limit(client, monkeypatch):
    monkeypatch.setattr(views, "ROOM_CREATION_OVERALL", RateLimiter(limit=2, window=3600))
    assert create(client, "203.0.113.1").status_code == 302
    assert create(client, "203.0.113.2").status_code == 302
    assert create(client, "203.0.113.3").status_code == 429


@pytest.mark.django_db
def test_full_room_turns_new_players_away(monkeypatch):
    monkeypatch.setattr(views, "MAX_PLAYERS_PER_ROOM", 2)
    room = Room.objects.create()
    room.participants.create(display_name="Ada")
    room.participants.create(display_name="Grace")

    response = Client().post(reverse("rooms:join", kwargs={"code": room.code}), {"display_name": "Linus"})
    assert response.status_code == 200
    assert b"This room is full" in response.content
    assert room.participants.count() == 2


# --- Expiry


@pytest.fixture
def rooms_of_various_ages():
    now = timezone.now()
    old = Room.objects.create(last_activity_at=now - timedelta(hours=25))
    old.participants.create(display_name="Ada")
    busy = Room.objects.create(last_activity_at=now - timedelta(hours=30))
    recent = Room.objects.create(last_activity_at=now - timedelta(hours=2))
    presence.connect(busy.code, 1)
    yield old, busy, recent
    presence.reset()


@pytest.mark.django_db
def test_expiry_deletes_only_idle_rooms_nobody_is_in(rooms_of_various_ages):
    old, busy, recent = rooms_of_various_ages
    assert delete_expired_rooms() == 1
    assert set(Room.objects.values_list("code", flat=True)) == {busy.code, recent.code}


@pytest.mark.django_db
def test_expiry_respects_setting(rooms_of_various_ages, settings):
    settings.ROOM_EXPIRY_HOURS = 1
    assert delete_expired_rooms() == 2  # old and recent; busy is still in use


@pytest.mark.django_db
def test_expire_rooms_command(rooms_of_various_ages, capsys):
    call_command("expire_rooms")
    assert "Deleted 1 expired room(s)." in capsys.readouterr().out


@pytest.mark.django_db
def test_creating_a_room_cleans_up_old_ones(client, rooms_of_various_ages):
    old, _, _ = rooms_of_various_ages
    create(client, "203.0.113.7")
    assert not Room.objects.filter(id=old.id).exists()
