import re

import pytest
from django.urls import reverse

from rooms import actions, decks
from rooms.forms import DeckForm
from rooms.models import Room

# --- Custom deck rules


def test_parse_custom_trims_and_drops_blanks_and_duplicates():
    assert decks.parse_custom(" 1, 2 ,, 4, 2, ?,") == ["1", "2", "4", "?"]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "at least 2"),
        ("5, 5", "at least 2"),
        ("1, 2, HUGE1", "at most 4 characters: HUGE1"),
        (", ".join(str(n) for n in range(16)), "at most 15 cards"),
    ],
)
def test_parse_custom_rejects_bad_decks(text, message):
    with pytest.raises(decks.DeckError, match=message):
        decks.parse_custom(text)


def test_key_for_recognises_presets_and_custom():
    assert decks.key_for(decks.FIBONACCI) == "fibonacci"
    assert decks.key_for(["XS", "S", "M", "L", "XL", "?", "☕"]) == "tshirt"
    assert decks.key_for(["1", "2", "3"]) == "custom"


# --- The form


def test_form_gives_preset_cards():
    form = DeckForm({"deck": "powers"})
    assert form.is_valid()
    assert form.cleaned_data["cards"] == ["1", "2", "4", "8", "16", "?", "☕"]


def test_form_gives_custom_cards():
    form = DeckForm({"deck": "custom", "custom": "S, M, L"})
    assert form.is_valid()
    assert form.cleaned_data["cards"] == ["S", "M", "L"]


def test_form_ignores_custom_text_for_presets():
    form = DeckForm({"deck": "tshirt", "custom": "this is ignored"})
    assert form.is_valid()
    assert form.cleaned_data["cards"][0] == "XS"


def test_form_rejects_unknown_deck_and_bad_custom():
    assert not DeckForm({"deck": "tarot"}).is_valid()
    form = DeckForm({"deck": "custom", "custom": "1"})
    assert not form.is_valid()
    assert "at least 2" in form.errors["custom"][0]


# --- Creating rooms


@pytest.mark.django_db
def test_create_room_with_tshirt_deck(client):
    client.post(reverse("rooms:create"), {"deck": "tshirt"})
    assert Room.objects.get().deck == ["XS", "S", "M", "L", "XL", "?", "☕"]


@pytest.mark.django_db
def test_create_room_with_custom_deck(client):
    client.post(reverse("rooms:create"), {"deck": "custom", "custom": "0, 1, 3, 5, ?"})
    assert Room.objects.get().deck == ["0", "1", "3", "5", "?"]


@pytest.mark.django_db
def test_invalid_custom_deck_shows_error_and_creates_nothing(client):
    response = client.post(reverse("rooms:create"), {"deck": "custom", "custom": "TOOLONG, 1"})
    assert response.status_code == 400
    assert b"at most 4 characters" in response.content
    assert not Room.objects.exists()


@pytest.mark.django_db
def test_room_page_preselects_current_deck(client):
    client.post(reverse("rooms:create"), {"deck": "custom", "custom": "A, B, C"})
    room = Room.objects.get()
    client.post(reverse("rooms:join", kwargs={"code": room.code}), {"display_name": "Ada"})
    page = client.get(room.get_absolute_url()).content.decode()
    assert re.search(r'value="custom"[^>]*checked', page)
    assert 'value="A, B, C"' in page


# --- Switching decks


@pytest.mark.django_db
def test_set_deck_starts_a_fresh_round():
    room = Room.objects.create()
    ada = room.participants.create(display_name="Ada", vote="5")
    Room.objects.filter(id=room.id).update(revealed=True)
    room.refresh_from_db()

    assert actions.set_deck(room, ["S", "M", "L"])
    room.refresh_from_db()
    ada.refresh_from_db()
    assert room.deck == ["S", "M", "L"]
    assert room.round == 2
    assert not room.revealed
    assert ada.vote == ""


@pytest.mark.django_db
def test_set_same_deck_is_not_a_change():
    room = Room.objects.create()
    assert not actions.set_deck(room, decks.FIBONACCI)
    room.refresh_from_db()
    assert room.round == 1
