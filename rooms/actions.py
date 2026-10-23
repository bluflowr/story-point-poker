"""
What players can do in a room. The consumer calls these with the room
freshly loaded from the database; each returns True if anything changed, so
the consumer knows whether to push an update to everyone.

Actions that depend on the round take the round number the player's page
was showing. If the room has moved on (say two people clicked "Next round"
at the same moment), the stale request is ignored instead of applied twice.
"""

from django.db import transaction
from django.db.models import F

from .models import Room

STORY_TITLE_MAX = Room._meta.get_field("story_title").max_length


def vote(room, participant_id, card, round_number):
    if room.revealed or room.round != round_number or card not in room.deck:
        return False
    participant = room.participants.filter(id=participant_id).first()
    if participant is None:
        return False
    # Picking the card you already chose takes the vote back.
    participant.vote = "" if participant.vote == card else card
    participant.save(update_fields=["vote"])
    return True


def reveal(room, round_number):
    return bool(Room.objects.filter(id=room.id, round=round_number, revealed=False).update(revealed=True))


def next_round(room, round_number):
    with transaction.atomic():
        advanced = Room.objects.filter(id=room.id, round=round_number).update(round=F("round") + 1, revealed=False)
        if advanced:
            room.participants.update(vote="")
    return bool(advanced)


def set_story(room, title):
    title = " ".join(title.split())[:STORY_TITLE_MAX]
    if title == room.story_title:
        return False
    room.story_title = title
    room.save(update_fields=["story_title"])
    return True


def set_deck(room, cards):
    """Switch decks. Starts a fresh round, since old votes may not exist in the new deck."""
    if list(cards) == room.deck:
        return False
    with transaction.atomic():
        Room.objects.filter(id=room.id).update(deck=list(cards), round=F("round") + 1, revealed=False)
        room.participants.update(vote="")
    return True
