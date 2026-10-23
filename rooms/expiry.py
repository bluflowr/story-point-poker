"""
Deleting rooms nobody has used for a while.

Runs inside the web process (see views.create_room): on Render the database
file lives on the web service's own disk, so a separate cron job couldn't
reach it.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone

from . import presence
from .limits import RateLimiter
from .models import Room

# At most one cleanup an hour.
_cleanup_due = RateLimiter(limit=1, window=60 * 60)


def delete_expired_rooms(now=None):
    """Delete idle rooms (and expired sessions). Returns how many rooms went."""
    cutoff = (now or timezone.now()) - timedelta(hours=settings.ROOM_EXPIRY_HOURS)
    # Someone may sit in a room for a long time without clicking anything.
    in_use = presence.active_room_codes()
    expired = Room.objects.filter(last_activity_at__lt=cutoff).exclude(code__in=in_use)
    count = expired.count()
    expired.delete()  # participants go with their room
    SessionStore.clear_expired()
    return count


def delete_expired_rooms_occasionally():
    if _cleanup_due.allow():
        delete_expired_rooms()
