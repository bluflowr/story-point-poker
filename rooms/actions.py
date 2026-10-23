"""
What players can do in a room, and who is allowed to do it.

The consumer calls these with the room freshly loaded from the database and
`actor`, the Participant who sent the action. Each returns True if anything
changed, so the consumer knows whether to push an update to everyone.
Anything not allowed simply returns False.

Actions that depend on the round take the round number the player's page
was showing. If the room has moved on (say two people clicked "Next round"
at the same moment), the stale request is ignored instead of applied twice.
"""

import math
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Room

STORY_TITLE_MAX = Room._meta.get_field("story_title").max_length


# --- Permissions


def is_facilitator(room, actor):
    return room.facilitator_id == actor.id


def can_control(room, actor):
    """Reveal, start rounds, and change the story or deck."""
    return not room.facilitator_only or is_facilitator(room, actor)


def can_take_over(room, actor, online_ids):
    """Anyone can step in when there is no facilitator, or they're offline."""
    return not is_facilitator(room, actor) and (room.facilitator_id is None or room.facilitator_id not in online_ids)


# --- Voting


def vote(room, actor, card, round_number):
    if actor.is_observer or room.revealed or room.round != round_number or card not in room.deck:
        return False
    # Picking the card you already chose takes the vote back.
    actor.vote = "" if actor.vote == card else card
    actor.save(update_fields=["vote"])
    return True


def reveal(room, actor, round_number):
    if not can_control(room, actor):
        return False
    revealed = Room.objects.filter(id=room.id, round=round_number, revealed=False)
    return bool(revealed.update(revealed=True, timer_ends_at=None))


def next_round(room, actor, round_number):
    if not can_control(room, actor):
        return False
    with transaction.atomic():
        advanced = Room.objects.filter(id=room.id, round=round_number).update(
            round=F("round") + 1, revealed=False, timer_ends_at=None
        )
        if advanced:
            room.participants.update(vote="")
    return bool(advanced)


def set_story(room, actor, title):
    if not can_control(room, actor):
        return False
    title = " ".join(title.split())[:STORY_TITLE_MAX]
    if title == room.story_title:
        return False
    room.story_title = title
    room.save(update_fields=["story_title"])
    return True


def set_deck(room, actor, cards):
    """Switch decks. Starts a fresh round, since old votes may not exist in the new deck."""
    if not can_control(room, actor) or list(cards) == room.deck:
        return False
    with transaction.atomic():
        Room.objects.filter(id=room.id).update(
            deck=list(cards), round=F("round") + 1, revealed=False, timer_ends_at=None
        )
        room.participants.update(vote="")
    return True


# --- Timer

TIMER_PRESETS = {30: "30s", 60: "1 min", 120: "2 min", 300: "5 min"}


def start_timer(room, actor, seconds):
    """Start (or restart) the round timer. Revealing or a new round clears it."""
    if not can_control(room, actor) or room.revealed or seconds not in TIMER_PRESETS:
        return False
    room.timer_ends_at = timezone.now() + timedelta(seconds=seconds)
    room.save(update_fields=["timer_ends_at"])
    return True


def stop_timer(room, actor):
    if not can_control(room, actor) or room.timer_ends_at is None:
        return False
    room.timer_ends_at = None
    room.save(update_fields=["timer_ends_at"])
    return True


def timer_seconds_left(room, now=None):
    """Whole seconds until the timer runs out (0 once it has), or None if no timer."""
    if room.timer_ends_at is None:
        return None
    left = (room.timer_ends_at - (now or timezone.now())).total_seconds()
    return max(0, math.ceil(left))


# --- Roles


def set_observing(room, actor, target_id, observing):
    """Switch between voting and observing: yourself, or anyone if you're the facilitator."""
    if target_id != actor.id and not is_facilitator(room, actor):
        return False
    target = room.participants.filter(id=target_id).first()
    if target is None or target.is_observer == observing:
        return False
    target.is_observer = observing
    if observing:
        target.vote = ""  # observers don't vote, so withdraw any vote
    target.save(update_fields=["is_observer", "vote"])
    return True


def hand_over(room, actor, target_id):
    if not is_facilitator(room, actor) or target_id == actor.id:
        return False
    target = room.participants.filter(id=target_id).first()
    if target is None:
        return False
    room.facilitator = target
    room.save(update_fields=["facilitator"])
    return True


def take_over(room, actor, online_ids):
    if not can_take_over(room, actor, online_ids):
        return False
    room.facilitator = actor
    room.save(update_fields=["facilitator"])
    return True


def set_facilitator_only(room, actor, facilitator_only):
    if not is_facilitator(room, actor) or room.facilitator_only == facilitator_only:
        return False
    room.facilitator_only = facilitator_only
    room.save(update_fields=["facilitator_only"])
    return True


def remove_player(room, actor, target_id):
    """The facilitator removes someone (not themselves). They can join again."""
    if not is_facilitator(room, actor) or target_id == actor.id:
        return False
    return bool(room.participants.filter(id=target_id).delete()[0])
