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

## Deploying to Render

The app runs on [Render](https://render.com) at https://story-point-poker-13a5.onrender.com. Everything Render needs is in `render.yaml`: the build and start commands, the health check, region (Virginia) and plan (Free).

### First deploy

1. **Put the code on GitHub.** On github.com, create a new **private** repository (e.g. `story-point-poker`) *without* a README, .gitignore or licence. Then, in the project folder:

   ```bash
   git remote add origin https://github.com/<your-username>/story-point-poker.git
   git push -u origin main
   ```

   If git asks for a password, GitHub wants a [personal access token](https://github.com/settings/tokens) (classic, with the `repo` scope) instead of your account password.

2. **Create the service on Render.** Sign in at https://dashboard.render.com, choose **New → Blueprint**, connect your GitHub account, pick the repository, and click **Apply**. Render reads `render.yaml`, generates a secret key, and starts the first build (a few minutes).

3. **Open the app** at the `https://….onrender.com` address shown on the service page and play a round.

### After that

Every `git push` to `main` deploys automatically. Watch progress and logs on the service's page in the Render dashboard.

Commands are run on Render, not on your machine. `render.yaml` is the place to change them:
- **Build:** `uv sync --frozen --no-dev && uv run --no-sync python manage.py collectstatic --noinput`
- **Start:** `.venv/bin/python manage.py migrate --noinput && .venv/bin/uvicorn config.asgi:application --host 0.0.0.0 --port $PORT ...`

### Good to know

- **Free plan:** the service sleeps after 15 minutes with no traffic, and the first visit afterwards takes about a minute. While a room page is open, it sends a small keep-alive message every 4 minutes (`static/js/connection.js`), so it won't fall asleep mid-session.
- **Rooms don't survive restarts or deploys.** The free plan has no lasting disk, so the SQLite database starts empty each time. Avoid deploying while your team is estimating.
- **To keep rooms across restarts:** upgrade to a paid plan, attach a disk (e.g. mounted at `/var/data`), and set `SQLITE_PATH=/var/data/db.sqlite3` in the Environment tab.
- **Keep it to one instance.** Online status and live updates live in the server's memory. More than one instance would need Redis (`channels_redis`).
- **Admin on Render:** only practical on a paid plan with a disk. Run `.venv/bin/python manage.py createsuperuser` from the service's **Shell** tab (Render doesn't offer a shell on the free plan). Without a disk, the login is lost on restart like everything else.
