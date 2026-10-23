"""
Who is this visitor? There are no accounts, so the Django session remembers
which Participant the browser is in each room it has joined.

Session layout:
    session["seats"] = {"<room code>": <participant id>, ...}
    session["display_name"] = "<last name used>"  # pre-fills the join form
"""

from .models import Participant

SEATS_KEY = "seats"
NAME_KEY = "display_name"


def get_participant(session, room):
    participant_id = session.get(SEATS_KEY, {}).get(room.code)
    if participant_id is None:
        return None
    # The participant row may have been deleted since the session was saved.
    return Participant.objects.filter(id=participant_id, room=room).first()


def remember_participant(session, participant):
    seats = session.get(SEATS_KEY, {})
    seats[participant.room.code] = participant.id
    # Reassign so Django notices the change and saves the session.
    session[SEATS_KEY] = seats
    session[NAME_KEY] = participant.display_name


def last_display_name(session):
    return session.get(NAME_KEY, "")
