from django.contrib import admin

from .models import Participant, Room


class ParticipantInline(admin.TabularInline):
    model = Participant
    extra = 0


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ["code", "story_title", "round", "revealed", "created_at", "last_activity_at"]
    search_fields = ["code", "story_title"]
    inlines = [ParticipantInline]
