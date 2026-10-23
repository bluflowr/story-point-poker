"""
Who is online right now, per room.

Kept in memory rather than the database: the app runs as a single process,
and presence doesn't need to survive a restart because browsers reconnect on
their own. If the app ever runs as several processes, this has to move to
Redis along with the channel layer.

Counts open connections per participant, so someone with two tabs open only
goes offline when both are closed.
"""

import threading
from collections import Counter, defaultdict

_lock = threading.Lock()
_connections = defaultdict(Counter)  # room code -> {participant id: open sockets}


def connect(room_code, participant_id):
    with _lock:
        _connections[room_code][participant_id] += 1


def disconnect(room_code, participant_id):
    with _lock:
        room = _connections[room_code]
        room[participant_id] -= 1
        if room[participant_id] <= 0:
            del room[participant_id]
        if not room:
            del _connections[room_code]


def online_ids(room_code):
    with _lock:
        return set(_connections.get(room_code, ()))


def reset():
    """Forget everyone. Used by tests."""
    with _lock:
        _connections.clear()
