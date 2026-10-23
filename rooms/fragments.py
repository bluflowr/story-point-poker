"""
Context for the page fragments that get pushed over the WebSocket.

The room view uses the same functions for the first page render, so the
initial HTML and the live updates always match.
"""

from . import presence


def participants_context(room, me_id, *, also_online=()):
    online = presence.online_ids(room.code) | set(also_online)
    participants = list(room.participants.all())
    return {
        "participants": participants,
        "online_ids": online,
        "online_count": sum(1 for p in participants if p.id in online),
        "me_id": me_id,
    }
