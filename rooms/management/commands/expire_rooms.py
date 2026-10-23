from django.conf import settings
from django.core.management.base import BaseCommand

from rooms.expiry import delete_expired_rooms


class Command(BaseCommand):
    help = (
        f"Delete rooms idle for more than ROOM_EXPIRY_HOURS (currently {settings.ROOM_EXPIRY_HOURS}). "
        "The app already does this by itself once an hour; this is for running it by hand. "
        "Run from a separate process, it can't see who is connected right now, so only idle time counts."
    )

    def handle(self, *args, **options):
        count = delete_expired_rooms()
        self.stdout.write(f"Deleted {count} expired room(s).")
