from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import JoinForm
from .fragments import participants_context
from .identity import get_participant, last_display_name, remember_participant
from .models import Room


def home(request):
    return render(request, "rooms/home.html")


@require_POST
def create_room(request):
    room = Room.objects.create()
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
            "room": room,
            "room_url": request.build_absolute_uri(room.get_absolute_url()),
            # Show the visitor as online straight away; their socket connects a moment later.
            **participants_context(room, participant.id, also_online=[participant.id]),
        },
    )


def join(request, code):
    room = get_object_or_404(Room, code=code)
    if get_participant(request.session, room) is not None:
        return redirect(room)

    form = JoinForm(request.POST or None, initial={"display_name": last_display_name(request.session)})
    if request.method == "POST" and form.is_valid():
        participant = room.participants.create(display_name=form.cleaned_data["display_name"])
        remember_participant(request.session, participant)
        room.touch()
        return redirect(room)

    return render(request, "rooms/join.html", {"room": room, "form": form})


def healthz(request):
    """Render pings this to check the app is up."""
    return HttpResponse("ok", content_type="text/plain")
