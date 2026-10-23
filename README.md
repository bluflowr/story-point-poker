# Story Point Poker

A planning poker app for estimating stories with your team in real time. It's built with Django, Django Channels and HTMX. See [PLAN.md](PLAN.md) for requirements and milestones.

## Local setup

You need [uv](https://docs.astral.sh/uv/), which installs the right Python version for you.

```bash
cp .env.example .env          # local settings (DEBUG on)
uv sync                       # create .venv and install dependencies
uv run python manage.py migrate
```

## Run the app

```bash
uv run uvicorn config.asgi:application --reload
```

Then open http://127.0.0.1:8000.

Use Uvicorn rather than `manage.py runserver`: plain `runserver` can't serve the WebSocket connections that make voting live.

## Tests and linting

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```

## Housekeeping

Rooms nobody has used for `ROOM_EXPIRY_HOURS` (default 24) are deleted automatically, at most once an hour, when someone creates a new room. Rooms with people connected are never deleted. To clean up by hand:

```bash
uv run python manage.py expire_rooms
```

Built-in limits (in `rooms/views.py` and `rooms/consumers.py`):
- 10 new rooms per IP address per 10 minutes, and 200 per hour overall
- 50 players per room
- 20 actions per connection per 10 seconds; larger-than-2KB messages are ignored
