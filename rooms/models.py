import secrets

from django.db import models
from django.urls import reverse
from django.utils import timezone

from .decks import default_deck

# No 0/o/1/l/i, so codes are easy to read aloud or retype.
ROOM_CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
ROOM_CODE_LENGTH = 10


def generate_room_code():
    return "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH))


class Room(models.Model):
    code = models.CharField(max_length=16, unique=True, default=generate_room_code)
    deck = models.JSONField(default=default_deck)
    story_title = models.CharField(max_length=200, blank=True)
    revealed = models.BooleanField(default=False)
    round = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.code

    def get_absolute_url(self):
        return reverse("rooms:room", kwargs={"code": self.code})

    def touch(self):
        """Mark the room as active so the expiry cleanup leaves it alone."""
        self.last_activity_at = timezone.now()
        self.save(update_fields=["last_activity_at"])


class Participant(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="participants")
    display_name = models.CharField(max_length=30)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["joined_at", "id"]

    def __str__(self):
        return f"{self.display_name} in {self.room}"
