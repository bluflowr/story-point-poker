# Story Point Poker

A planning poker app for estimating stories with your team in real time. It's built with Django, Django Channels and HTMX. See [PLAN.md](PLAN.md) for requirements and milestones.

## Local setup

You need [uv](https://docs.astral.sh/uv/), which installs the right Python version (3.12) and all dependencies for you.

```bash
# Install uv once (puts it in ~/.local/bin), and make sure that folder is on your PATH
curl -LsSf https://astral.sh/uv/install.sh | sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bash_profile && source ~/.bash_profile
```

Then, in the project folder:

```bash
cp .env.example .env              # local settings (DEBUG on)
uv sync                           # create .venv and install dependencies
uv run python manage.py migrate   # create the local database
```

Always run Python through `uv run` (e.g. `uv run python manage.py ...`). Plain `python3` may pick up a different Python version that doesn't have the project's packages.

## Run the app

```bash
uv run uvicorn config.asgi:application --reload
```

Then open http://127.0.0.1:8000. `--reload` restarts the server when you edit code.

Use Uvicorn rather than `manage.py runserver`: plain `runserver` can't serve the WebSocket connections that make voting live.

To try it as several people, open the room link in a private window or a different browser.

## Admin

Django's admin at http://127.0.0.1:8000/admin/ lets you look at rooms and players. Create a login for it first:

```bash
uv run python manage.py createsuperuser
```

## Database changes

After pulling new code, apply any new migrations:

```bash
uv run python manage.py migrate
```

After changing a model in `rooms/models.py`, create a migration and commit it along with the change:

```bash
uv run python manage.py makemigrations rooms
uv run python manage.py migrate
```

## Tests and linting

```bash
uv run pytest                              # everything
uv run pytest tests/test_voting.py         # one file
uv run pytest -k reveal                    # tests whose names contain "reveal"
uv run ruff check .                        # find problems (add --fix to fix the simple ones)
uv run ruff format .                       # format the code
```

## Settings

Settings come from environment variables. Locally they live in `.env` (copied from `.env.example`); on Render they go in the service's Environment tab.

| Variable | Default | What it does |
|---|---|---|
| `DJANGO_DEBUG` | `false` | `true` for local development only. Shows detailed error pages and turns off the HTTPS-only security settings. |
| `DJANGO_SECRET_KEY` | (none) | Required when debug is off. A long random string; keep it secret. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hostnames the site answers to. On Render, the service's own hostname is added automatically. |
| `SQLITE_PATH` | `db.sqlite3` in the project folder | Where the database file lives. |
| `ROOM_EXPIRY_HOURS` | `24` | How long a room can sit unused before it is deleted. |

## Housekeeping

Rooms nobody has used for `ROOM_EXPIRY_HOURS` are deleted automatically, at most once an hour, when someone creates a new room. Rooms with people connected are never deleted. To clean up by hand:

```bash
uv run python manage.py expire_rooms
```

Built-in limits (in `rooms/views.py` and `rooms/consumers.py`):
- 10 new rooms per IP address per 10 minutes, and 200 per hour overall
- 50 players per room
- 20 actions per connection per 10 seconds; larger-than-2KB messages are ignored
