from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .expiry import delete_expired_rooms_occasionally
from .forms import DeckForm, JoinForm, RoomOptionsForm
from .fragments import board_context
from .identity import created, get_participant, last_display_name, remember_created, remember_participant
from .limits import RateLimiter, client_ip
from .models import Room

# Generous for a team, but stops a script from filling the database.
ROOM_CREATION_PER_IP = RateLimiter(limit=10, window=10 * 60)
ROOM_CREATION_OVERALL = RateLimiter(limit=200, window=60 * 60)
MAX_PLAYERS_PER_ROOM = 50


def home(request):
    return render(request, "rooms/home.html", {"deck_form": DeckForm(), "options_form": RoomOptionsForm()})


@require_POST
def create_room(request):
    deck_form = DeckForm(request.POST)
    options_form = RoomOptionsForm(request.POST)
    context = {"deck_form": deck_form, "options_form": options_form}
    if not (deck_form.is_valid() and options_form.is_valid()):
        return render(request, "rooms/home.html", context, status=400)

    if not (ROOM_CREATION_PER_IP.allow(client_ip(request)) and ROOM_CREATION_OVERALL.allow()):
        context["error"] = "Too many new rooms just now. Please wait a few minutes."
        return render(request, "rooms/home.html", context, status=429)

    delete_expired_rooms_occasionally()
    room = Room.objects.create(
        deck=deck_form.cleaned_data["cards"],
        facilitator_only=options_form.cleaned_data["control"] == "facilitator",
    )
    remember_created(request.session, room)
    return redirect(room)


def room(request, code):
    room = get_object_or_404(Room, code=code)
    participant = get_participant(request.session, room)
    if participant is None:
        return redirect("rooms:join", code=room.code)

    return render(
        request,
        "rooms/room.html",
        {
            "room_url": request.build_absolute_uri(room.get_absolute_url()),
            "deck_form": DeckForm.for_room(room),
            # Show the visitor as online straight away; their socket connects a moment later.
            **board_context(room, participant.id, also_online=[participant.id]),
        },
    )


def join(request, code):
    room = get_object_or_404(Room, code=code)
    if get_participant(request.session, room) is not None:
        return redirect(room)

    form = JoinForm(request.POST or None, initial={"display_name": last_display_name(request.session)})
    if request.method == "POST" and room.participants.count() >= MAX_PLAYERS_PER_ROOM:
        form.add_error(None, f"This room is full ({MAX_PLAYERS_PER_ROOM} players).")
    elif request.method == "POST" and form.is_valid():
        participant = room.participants.create(
            display_name=form.cleaned_data["display_name"],
            is_observer=form.cleaned_data["observer"],
        )
        remember_participant(request.session, participant)
        if room.facilitator_id is None and created(request.session, room):
            room.facilitator = participant
            room.save(update_fields=["facilitator"])
        room.touch()
        return redirect(room)

    return render(request, "rooms/join.html", {"room": room, "form": form})


def healthz(request):
    """Render pings this to check the app is up."""
    return HttpResponse("ok", content_type="text/plain")
