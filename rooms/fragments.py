"""
Context for the page fragments that get pushed over the WebSocket.

The room view uses the same function for the first page render, so the
initial HTML and the live updates always match.

Each viewer gets their own render. Before the reveal, the context holds the
viewer's own card and only a yes/no for everyone else, so other people's
votes never reach the browser early. Which buttons appear also depends on
the viewer's role; actions.py checks permissions again when they're used.
"""

from . import actions, presence
from .results import suggest, summarize


def board_context(room, me_id, *, also_online=()):
    online = presence.online_ids(room.code) | set(also_online)
    participants = list(room.participants.all())
    me = next((p for p in participants if p.id == me_id), None)

    players = [
        {
            "id": p.id,
            "name": p.display_name,
            "is_me": p.id == me_id,
            "online": p.id in online,
            "is_observer": p.is_observer,
            "is_facilitator": p.id == room.facilitator_id,
            "has_voted": bool(p.vote),
            "card": p.vote if room.revealed else None,
        }
        for p in participants
    ]
    voters = [p for p in players if not p["is_observer"]]
    facilitator = next((p for p in players if p["is_facilitator"]), None)
    votes = [p.vote for p in participants if p.vote]
    results = summarize(votes, room.deck) if room.revealed else None
    stories = list(room.stories.all())

    return {
        "room": room,
        "players": players,
        "online_count": sum(1 for p in players if p["online"]),
        "voted_count": len(votes),
        # Offline voters only count if they voted before leaving.
        "voter_count": sum(1 for p in voters if p["online"] or p["has_voted"]),
        "me_id": me_id,
        "my_vote": me.vote if me else "",
        "i_observe": bool(me and me.is_observer),
        "facilitator": facilitator,
        "i_facilitate": bool(me and actions.is_facilitator(room, me)),
        "i_control": bool(me and actions.can_control(room, me)),
        "i_can_take_over": bool(me and actions.can_take_over(room, me, online)),
        "results": results,
        "stories": [
            {
                "id": story.id,
                "title": story.title,
                "estimate": story.estimate,
                "is_current": story.id == room.current_story_id,
            }
            for story in stories
        ],
        "estimated_count": sum(1 for story in stories if story.estimate),
        "waiting_count": sum(1 for story in stories if not story.estimate and story.id != room.current_story_id),
        "suggested_estimate": suggest(results, room.deck) if results else "",
        # Coffee means "break", not an estimate.
        "estimate_choices": [card for card in room.deck if card != "☕"],
        "timer_left": actions.timer_seconds_left(room),
        "timer_presets": actions.TIMER_PRESETS.items(),
    }
