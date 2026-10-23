import pytest

from rooms import actions
from rooms.models import Room

pytestmark = pytest.mark.django_db


@pytest.fixture
def room():
    return Room.objects.create()


@pytest.fixture
def ada(room):
    return room.participants.create(display_name="Ada")


def fresh(obj):
    obj.refresh_from_db()
    return obj


def test_vote_records_card(room, ada):
    assert actions.vote(room, ada.id, "5", room.round)
    assert fresh(ada).vote == "5"


def test_changing_vote(room, ada):
    actions.vote(room, ada.id, "5", room.round)
    actions.vote(room, ada.id, "8", room.round)
    assert fresh(ada).vote == "8"


def test_voting_same_card_again_takes_vote_back(room, ada):
    actions.vote(room, ada.id, "5", room.round)
    assert actions.vote(room, ada.id, "5", room.round)
    assert fresh(ada).vote == ""


def test_card_must_be_in_deck(room, ada):
    assert not actions.vote(room, ada.id, "40", room.round)
    assert fresh(ada).vote == ""


def test_cannot_vote_after_reveal(room, ada):
    actions.reveal(room, room.round)
    assert not actions.vote(fresh(room), ada.id, "5", room.round)


def test_vote_from_stale_round_is_ignored(room, ada):
    assert not actions.vote(room, ada.id, "5", room.round - 1)


def test_reveal_once(room):
    assert actions.reveal(room, room.round)
    assert fresh(room).revealed
    assert not actions.reveal(room, room.round)


def test_next_round_clears_votes_and_hides_cards(room, ada):
    actions.vote(room, ada.id, "5", 1)
    actions.reveal(room, 1)
    assert actions.next_round(fresh(room), 1)
    room = fresh(room)
    assert room.round == 2
    assert not room.revealed
    assert fresh(ada).vote == ""


def test_simultaneous_next_round_clicks_advance_once(room, ada):
    assert actions.next_round(room, 1)
    actions.vote(fresh(room), ada.id, "8", 2)  # someone votes in the new round
    assert not actions.next_round(room, 1)  # the second, late click
    assert fresh(room).round == 2
    assert fresh(ada).vote == "8"


def test_set_story_tidies_whitespace_and_limits_length(room):
    assert actions.set_story(room, "  PROJ-1   Login   page ")
    assert fresh(room).story_title == "PROJ-1 Login page"
    actions.set_story(room, "x" * 500)
    assert len(fresh(room).story_title) == actions.STORY_TITLE_MAX


def test_set_story_unchanged_is_not_a_change(room):
    actions.set_story(room, "PROJ-1")
    assert not actions.set_story(fresh(room), "PROJ-1")
