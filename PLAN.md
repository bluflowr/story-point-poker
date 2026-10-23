# Story Point Poker — Project Plan

## Decisions so far
| Topic | Decision |
|---|---|
| Audience | International team, ~5–15 people per session, reached at a public URL |
| Identity | Anonymous: enter a display name, share a room link. No accounts. |
| Persistence | Rooms are temporary and expire after inactivity |
| Stack | Django 5.2 + Django Channels (WebSockets) + HTMX, served by Uvicorn. SQLite. One server process with the in-memory channel layer (Redis only if we ever need more than one process). Python 3.12 managed by uv. |
| Hosting | Render web service with HTTPS and deploy-on-push from GitHub. A single instance; we'd add Redis only if we ever needed more than one. |

## Requirements

### Functional (MVP)
1. **Create room.** One click creates a room and gives it a shareable URL with an unguessable code (e.g. `/r/k7x2qp9mfa`, 10+ random characters), since the site is public.
2. **Join room.** Visiting the link asks for a display name, which is remembered in the Django session so a refresh doesn't ask again.
3. **Participant list.** Shows everyone in the room, live: who has voted (✓) and who hasn't, plus online/offline status.
4. **Decks.** The room creator picks a deck. Anyone can switch it between rounds; switching clears the current round.
   - **Fibonacci (default):** `1, 2, 3, 5, 8, 13, ?, ☕`
   - **T-shirt:** `XS, S, M, L, XL, ?, ☕`
   - **Powers of 2:** `1, 2, 4, 8, 16, ?, ☕`
   - **Custom:** comma-separated values typed in when the room is created, at most 15 cards of up to 4 characters each
5. **Vote.** Pick a card from the room's deck. You can change your vote until reveal.
6. **Reveal.** Anyone can reveal. All votes flip at once, with a summary:
   - Numeric decks: average, min/max, and a highlight when everyone agrees
   - Non-numeric decks (T-shirt, custom): a count per card and the most common pick
   - `?` and `☕` are left out of the stats
7. **Reset / next round.** Anyone can reset. It clears all votes for the next story. An optional free-text "current story" label sits at the top of the room.
8. **Expiry.** Rooms with no activity for N hours (default 24) are deleted by a cleanup command.

### Non-functional
- **No peeking.** The server never sends vote values to browsers before reveal; it only sends "has voted".
- **Resilient.** Browsers reconnect automatically after a dropped connection or laptop sleep. Refreshing the page keeps your seat and your vote.
- **Fast enough.** Updates show up for everyone in under ~300 ms on a normal connection.
- **Usable.** Works on phones (some people vote from their phone during calls) and in the latest Chrome, Firefox, Safari and Edge.
- **Minimal JavaScript.** HTMX plus its WebSocket extension, with no hand-written JS framework.
- **Simple to run.** Locally, run `uv run uvicorn config.asgi:application --reload`; no Docker needed. On Render, it deploys automatically when you push to `main`.
- **Safe on the public internet.**
  - HTTPS (provided by Render)
  - `DEBUG=False` and a secret key in environment variables
  - WebSocket origin checking (`AllowedHostsOriginValidator`)
  - CSRF on forms
  - Length limits on names, story titles and custom decks
  - Basic rate limiting on room creation

### Out of scope for MVP (candidates for later)
- Story queue with recorded estimates and CSV export
- Facilitator and observer roles, a round timer
- Jira/Linear/GitHub import and write-back
- Accounts and history

## Architecture sketch
```
Browser (Django templates + HTMX ws extension)
   │  HTTP: create/join room, initial page render
   │  WebSocket: vote / reveal / reset → server
   │             ← server pushes re-rendered HTML fragments
   ▼
Django (ASGI via Uvicorn)
   ├─ views.py      – room create/join pages
   ├─ consumers.py  – RoomConsumer: handles WS messages, broadcasts to room group
   ├─ models.py     – Room, Participant, Vote (SQLite)
   └─ In-memory channel layer – fan-out to everyone in the room (single process)
```
How a vote travels: you click a card → HTMX sends `{"action":"vote","value":"5"}` over the socket → the consumer saves it → the consumer broadcasts to the room group → each connected consumer renders the participant-list fragment *for its own user* → HTMX swaps it into the page by element id.

## Data model (draft)
- **Room**: `code` (slug, unique), `deck` (list of card strings, JSONField; presets live in code), `story_title`, `revealed` (bool), `round` (int), `created_at`, `last_activity_at`
- **Participant**: `room` FK, `session_key`, `display_name`, `is_connected`, `joined_at`
- **Vote**: `participant` FK, `round`, `value` (str); unique on (participant, round)

## Milestones
| # | Milestone | Deliverable |
|---|---|---|
| 0 ✅ | Project setup | Django project, Channels + Uvicorn, HTMX vendored in `static/vendor`, env-based settings, pytest + pytest-django, ruff |
| 1 | Rooms & joining | Create/join flow and display name in session. The room page renders statically, with no realtime yet. |
| 2 | Realtime presence | `RoomConsumer`, live participant list with online/offline status |
| 3 | Voting loop | Vote, reveal, reset and the results summary; votes hidden server-side until reveal |
| 3b | Decks | Preset and custom decks, deck picker at room creation, switching decks between rounds, stats for non-numeric decks |
| 4 | Hardening | Reconnect handling, room expiry command, mobile layout, consumer tests (Channels `WebsocketCommunicator`) |
| 5 | Deploy | Production settings, `render.yaml` blueprint, GitHub repo connected to Render, and a smoke test with people on different continents |
| 6+ | Extras | Pick from the "later" list |

## Render notes
- **Free plan:** good for development and trying things out. It sleeps after about 15 minutes idle, so the first visit takes about 30 seconds to wake it.
- **Paid plan (around $7/month):** use this once the team relies on it. It's always on, so there's no wake-up delay at the start of a session.
- **Data:** SQLite lives on the instance's local disk, so active rooms are lost on each redeploy or restart. Rooms are temporary, so that's acceptable. Avoid deploying during a session. If that becomes a nuisance, switch to Render Postgres. It's a settings change.
- **Scale:** keep it at one instance. More than one would need the Redis channel layer.

## Open questions
1. Which Render region? Pick the one closest to most of the team, or in the middle of them; Frankfurt or Virginia (US East) are usually good middles for Europe + Americas. You can decide this at deploy time.
2. Room passcodes (optional, later): anyone with a room link can join. Do we want an optional passcode per room?
