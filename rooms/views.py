from django.http import HttpResponse
from django.shortcuts import render


def home(request):
    return render(request, "rooms/home.html")


def healthz(request):
    """Render pings this to check the app is up."""
    return HttpResponse("ok", content_type="text/plain")
