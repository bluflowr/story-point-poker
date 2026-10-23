"""
The room's WebSocket connection.

Each open room page has one RoomConsumer. When anything about the room
changes, a message goes to the room's group, and every consumer in it
re-renders the room for its own participant and sends the HTML down the
socket. The htmx ws extension swaps it into the page by element id.

Players' actions arrive as JSON from forms marked `ws-send`, e.g.
{"action": "vote", "round": "3", "value": "5"} or
{"action": "deck", "deck": "custom", "custom": "1, 2, 4"}.
"""

import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.template.loader import render_to_string

from . import actions, presence
from .forms import DeckForm
from .fragments import board_context
from .identity import get_participant
from .models import Room


def group_name(room_code):
    return f"room_{room_code}"


class RoomConsumer(AsyncWebsocketConsumer):
    participant_id = None

    async def connect(self):
        self.room_code = self.scope["url_route"]["kwargs"]["code"]
        self.group = group_name(self.room_code)

        self.participant_id = await self.find_participant()
        if self.participant_id is None:
            # Not a member of this room (or it doesn't exist): refuse.
            await self.close()
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
        try:
            message = json.loads(text_data or "")
        except json.JSONDecodeError:
            return
        if not isinstance(message, dict):
            return

        changed, deck_error = await self.apply_action(message)
        if deck_error:
            # Only the person who made the mistake needs to see it.
            await self.send(text_data=render_to_string("rooms/_deck_error.html", {"deck_error": deck_error}))
        if changed:
            await self.broadcast_change()

    async def broadcast_change(self):
        await self.channel_layer.group_send(self.group, {"type": "room.changed"})

    # Group message handlers. Channels maps "room.changed" to room_changed.

    async def room_changed(self, event):
        html = await self.render_room()
        if html:
            await self.send(text_data=html)

    # Database work runs in a thread, since the ORM is synchronous.

    @database_sync_to_async
    def find_participant(self):
        room = Room.objects.filter(code=self.room_code).first()
        if room is None:
            return None
        participant = get_participant(self.scope["session"], room)
        if participant is None:
            return None
        room.touch()
        return participant.id

    @database_sync_to_async
    def apply_action(self, message):
        """Returns (changed, deck_error)."""
        room = Room.objects.filter(code=self.room_code).first()
        if room is None:
            return False, None

        action = message.get("action")
        if action == "story":
            changed = actions.set_story(room, str(message.get("title", "")))
        elif action == "deck":
            form = DeckForm(data=message)
            if not form.is_valid():
                errors = [error for field_errors in form.errors.values() for error in field_errors]
                return False, " ".join(errors)
            changed = actions.set_deck(room, form.cleaned_data["cards"])
        else:
            try:
                round_number = int(message.get("round"))
            except (TypeError, ValueError):
                return False, None
            if action == "vote":
                changed = actions.vote(room, self.participant_id, str(message.get("value", "")), round_number)
            elif action == "reveal":
                changed = actions.reveal(room, round_number)
            elif action == "next_round":
                changed = actions.next_round(room, round_number)
            else:
                return False, None

        if changed:
            room.touch()
        return changed, None

    @database_sync_to_async
    def render_room(self):
        room = Room.objects.filter(code=self.room_code).first()
        if room is None:
            return None
        return render_to_string("rooms/_live.html", board_context(room, self.participant_id))
