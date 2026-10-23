"""
The room's WebSocket connection.

Each open room page has one RoomConsumer. When anything about the room
changes, a message goes to the room's group, and every consumer in it
re-renders the room for its own participant and sends the HTML down the
socket. The htmx ws extension swaps it into the page by element id.

Players' actions arrive as JSON from forms marked `ws-send`, e.g.
{"action": "vote", "round": "3", "value": "5"},
{"action": "deck", "deck": "custom", "custom": "1, 2, 4"} or
{"action": "remove", "target": "12"}. Who may do what lives in actions.py.
"""

import json
from dataclasses import dataclass

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.template.loader import render_to_string

from . import actions, presence
from .forms import DeckForm
from .fragments import board_context
from .identity import get_participant
from .limits import RateLimiter
from .models import Room


@dataclass
class Outcome:
    """What an action did, so receive() knows what to send."""

    changed: bool = False
    deck_error: str | None = None
    removed_id: int | None = None


def _int(value):
    """Numbers arrive as strings from forms; anything else becomes None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def group_name(room_code):
    return f"room_{room_code}"


# Custom close codes (4000-4999 are free for apps). The htmx ws extension only
# reconnects after unexpected drops (1006, 1012, 1013), so these stop it from
# retrying a connection that can never succeed.
CLOSE_ROOM_GONE = 4404
CLOSE_NOT_SEATED = 4403

# Anything bigger than this isn't a real form submission.
MAX_MESSAGE_LENGTH = 2000


class RoomConsumer(AsyncWebsocketConsumer):
    participant_id = None
    # Per connection: plenty for clicking around, too few for a flood.
    message_limit = 20
    message_window = 10  # seconds

    async def connect(self):
        self.room_code = self.scope["url_route"]["kwargs"]["code"]
        self.group = group_name(self.room_code)
        self.limiter = RateLimiter(self.message_limit, self.message_window)

        self.participant_id, problem = await self.find_participant()
        if problem:
            # Accept just long enough to tell the page what's wrong, then close
            # with a code that stops the browser from retrying.
            await self.accept()
            notice = render_to_string("rooms/_notice.html", {"problem": problem, "room_code": self.room_code})
            await self.send(text_data=notice)
            await self.close(code=CLOSE_ROOM_GONE if problem == "gone" else CLOSE_NOT_SEATED)
            return

        presence.connect(self.room_code, self.participant_id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.broadcast_change()

    async def disconnect(self, code):
        if self.participant_id is None:
            return
        presence.disconnect(self.room_code, self.participant_id)
        await self.channel_layer.group_discard(self.group, self.channel_name)
        await self.broadcast_change()

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data or len(text_data) > MAX_MESSAGE_LENGTH or not self.limiter.allow():
            return
        try:
            message = json.loads(text_data)
        except json.JSONDecodeError:
            return
        if not isinstance(message, dict):
            return

        outcome = await self.apply_action(message)
        if outcome.deck_error:
            # Only the person who made the mistake needs to see it.
            await self.send(text_data=render_to_string("rooms/_deck_error.html", {"deck_error": outcome.deck_error}))
        if outcome.removed_id:
            await self.channel_layer.group_send(
                self.group, {"type": "player.removed", "participant_id": outcome.removed_id}
            )
        if outcome.changed:
            await self.broadcast_change()

    async def broadcast_change(self):
        await self.channel_layer.group_send(self.group, {"type": "room.changed"})

    # Group message handlers. Channels maps "room.changed" to room_changed.

    async def room_changed(self, event):
        html = await self.render_room()
        if html:
            await self.send(text_data=html)

    async def player_removed(self, event):
        """The facilitator removed someone; if it's us, say so and stop."""
        if event["participant_id"] != self.participant_id:
            return
        notice = render_to_string("rooms/_notice.html", {"problem": "removed", "room_code": self.room_code})
        await self.send(text_data=notice)
        await self.close(code=CLOSE_NOT_SEATED)

    # Database work runs in a thread, since the ORM is synchronous.

    @database_sync_to_async
    def find_participant(self):
        """Returns (participant id, None), or (None, "gone" / "not_seated")."""
        room = Room.objects.filter(code=self.room_code).first()
        if room is None:
            return None, "gone"
        participant = get_participant(self.scope["session"], room)
        if participant is None:
            return None, "not_seated"
        room.touch()
        return participant.id, None

    @database_sync_to_async
    def apply_action(self, message):
        room = Room.objects.filter(code=self.room_code).first()
        actor = room and room.participants.filter(id=self.participant_id).first()
        action = message.get("action")
        if actor is None or action == "ping":
            # No longer in the room, or a keep-alive from connection.js.
            return Outcome()

        if action == "deck":
            form = DeckForm(data=message)
            if not form.is_valid():
                errors = [error for field_errors in form.errors.values() for error in field_errors]
                return Outcome(deck_error=" ".join(errors))
            changed = actions.set_deck(room, actor, form.cleaned_data["cards"])
        elif action == "story":
            changed = actions.set_story(room, actor, str(message.get("title", "")))
        elif action == "vote":
            changed = actions.vote(room, actor, str(message.get("value", "")), _int(message.get("round")))
        elif action == "reveal":
            changed = actions.reveal(room, actor, _int(message.get("round")))
        elif action == "next_round":
            changed = actions.next_round(room, actor, _int(message.get("round")))
        elif action == "observe":
            observing = message.get("observing") == "true"
            changed = actions.set_observing(room, actor, _int(message.get("target")), observing)
        elif action == "hand_over":
            changed = actions.hand_over(room, actor, _int(message.get("target")))
        elif action == "take_over":
            changed = actions.take_over(room, actor, presence.online_ids(room.code))
        elif action == "facilitator_only":
            changed = actions.set_facilitator_only(room, actor, message.get("value") == "true")
        elif action == "remove":
            target = _int(message.get("target"))
            if not actions.remove_player(room, actor, target):
                return Outcome()
            room.touch()
            return Outcome(changed=True, removed_id=target)
        else:
            return Outcome()

        if changed:
            room.touch()
        return Outcome(changed=changed)

    @database_sync_to_async
    def render_room(self):
        room = Room.objects.filter(code=self.room_code).first()
        if room is None:
            return None
        return render_to_string("rooms/_live.html", board_context(room, self.participant_id))
