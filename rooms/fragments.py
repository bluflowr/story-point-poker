"""
Context for the page fragments that get pushed over the WebSocket.

The room view uses the same function for the first page render, so the
initial HTML and the live updates always match.

Each viewer gets their own render. Before the reveal, the context holds the
viewer's own card and only a yes/no for everyone else, so other people's
votes never reach the browser early.
"""

from . import presence
from .results import summarize


def board_context(room, me_id, *, also_online=()):
    online = presence.online_ids(room.code) | set(also_online)
    participants = list(room.participants.all())

    players = [
        {
            "name": p.display_name,
            "is_me": p.id == me_id,
            "online": p.id in online,
            "has_voted": bool(p.vote),
            "card": p.vote if room.revealed else None,
        }
        for p in participants
    ]
    votes = [p.vote for p in participants if p.vote]
    my_vote = next((p.vote for p in participants if p.id == me_id), "")

    return {
        "room": room,
        "players": players,
        "online_count": sum(1 for p in players if p["online"]),
        "voted_count": len(votes),
        # Offline players only count if they voted before leaving.
        "voter_count": sum(1 for p in players if p["online"] or p["has_voted"]),
        "my_vote": my_vote,
        "results": summarize(votes, room.deck) if room.revealed else None,
    }
