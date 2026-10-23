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
