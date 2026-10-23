from django.urls import path

from . import views

app_name = "rooms"

urlpatterns = [
    path("", views.home, name="home"),
    path("rooms/new", views.create_room, name="create"),
    path("r/<slug:code>/", views.room, name="room"),
    path("r/<slug:code>/join", views.join, name="join"),
    path("r/<slug:code>/export.csv", views.export_csv, name="export"),
    path("healthz", views.healthz, name="healthz"),
]
