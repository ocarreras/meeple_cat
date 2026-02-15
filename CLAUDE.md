# CLAUDE.md — meeple.cat development guide

## What is this project?

meeple.cat is a board game platform where users play against humans or AI in real-time. It's designed as a plugin platform — adding a new game should only require game logic and UI components. First game: Carcassonne.

Domain: `play.meeple.cat`

## Monorepo structure

```
meeple/
├── backend/          Python (FastAPI) — REST API, WebSocket, game engine
├── frontend/         TypeScript (Next.js 16, React 19) — web client
├── infra/            Docker Compose, nginx, deploy scripts (AWS EC2)
├── docs/             Design documents (00-08) — READ THESE FIRST
├── docker-compose.yml        Local dev (postgres + redis + backend + frontend)
└── docker-compose.prod.yml   Production (adds nginx, certbot volumes)
```

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async), Pydantic 2 |
| Database | PostgreSQL 16, Redis 7 |
| Frontend | Next.js 16 (App Router), React 19, TypeScript 5, Tailwind 4, Zustand 5 |
| Auth | Google OIDC → JWT (HttpOnly cookies) |
| Package mgmt | uv (backend), npm (frontend) |
| Infra | Docker Compose on AWS EC2 (t3.medium), nginx reverse proxy |

## Local development

```bash
# Start postgres + redis
docker compose up -d postgres redis

# Backend (from repo root)
cd backend
uv sync
cp .env.example .env  # if needed, set MEEPLE_ prefixed vars
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (from repo root)
cd frontend
npm install
npm run dev
```

Backend runs on http://localhost:8000, frontend on http://localhost:3000.

All backend settings use `MEEPLE_` env prefix (see `backend/src/config.py`).

## Backend architecture

### Game engine (the heart of the platform)

The engine is in `backend/src/engine/` and uses a **plugin-based, phase-based state machine** with event sourcing:

- **`protocol.py`** — `GamePlugin` protocol that every game must implement
- **`session.py`** — `GameSession` orchestrates a single active game
- **`session_manager.py`** — manages all active sessions, handles recovery
- **`state_store.py`** — Redis for hot game state
- **`event_store.py`** — Postgres append-only event log
- **`registry.py`** — auto-discovers game plugins from `backend/src/games/`

Key flow: client sends action via WebSocket → `GameSession.apply_action()` validates → updates state in Redis → appends event to Postgres → broadcasts `PlayerView` to all connected clients.

### Game plugins

Games live in `backend/src/games/<game_name>/`. Each must implement `GamePlugin` protocol from `engine/protocol.py`.

Currently implemented: **Carcassonne** (`backend/src/games/carcassonne/`)
- `plugin.py` — main plugin class
- `tiles.py` — 72 tile definitions
- `board.py` — board representation
- `features.py` — feature tracking and merging (cities, roads, fields, monasteries)
- `scoring.py` — in-game and end-game scoring
- `meeples.py` — meeple placement validation

### API structure

REST under `/api/v1/`:
- `api/auth.py` — token refresh, /me endpoint
- `api/games.py` — game catalog
- `api/rooms.py` — lobby CRUD, join, start
- `api/matches.py` — match state, events
- `api/users.py` — user profiles

Auth (OIDC): `auth/routes.py`, `auth/jwt.py`, `auth/providers.py`

WebSocket: `ws/handler.py` at `/ws/game/{match_id}` — uses ticket-based auth

### Database

- Models in `backend/src/models/` (user, room, match, base, database)
- Auth models in `backend/src/auth/models.py` (UserAuth for multi-provider support)
- Tables are created via `Base.metadata.create_all` in main.py lifespan (NOT Alembic yet for schema creation)
- Manual ALTER TABLE migrations in `main.py` lifespan (lines 47-55) — this is tech debt

## Frontend architecture

- Next.js App Router with pages in `frontend/src/app/`
- Key pages: `/` (landing), `/login`, `/lobby` (room list), `/lobby/[roomId]` (room), `/game/[matchId]` (active game), `/profile/[userId]`
- Game UI uses canvas rendering (`components/game/BoardCanvas.tsx`)
- Carcassonne-specific components in `components/games/carcassonne/`
- API client in `lib/api.ts`, types in `lib/types.ts`
- Auth state managed via `AuthInitializer.tsx` component

## Running tests

```bash
# Backend tests (from backend/)
uv run pytest

# Backend tests with verbose output
uv run pytest -v

# Specific test file
uv run pytest tests/games/carcassonne/test_scoring.py
```

No frontend tests yet.

## Deployment

Current setup: AWS EC2 (t3.medium, eu-central-1), deployed via rsync scripts.

```bash
# Deploy everything
./infra/deploy-update.sh all

# Deploy only backend (with migrations)
./infra/deploy-update.sh backend --migrate

# Deploy only frontend
./infra/deploy-update.sh frontend

# First-time setup (provisions EC2, sets up DNS)
DOMAIN=play.meeple.cat ./infra/aws-deploy.sh

# Add TLS (run on server)
sudo ./infra/setup-tls.sh play.meeple.cat
```

Deploy host: `DEPLOY_HOST` env var or hardcoded IP. SSH key at `~/.ssh/meeple-deploy.pem`.

### Known infra issues

- **Zero-downtime deploys not possible** — `deploy-update.sh` runs `docker compose up -d --build` which stops the running container, builds the new image on the server (minutes on t3.medium), then starts it. During the entire build+startup, nginx proxies to nothing → full outage. For a game platform this is especially bad: all active WebSocket connections drop, players mid-game lose their session. Needs a blue-green or rolling deploy strategy (build image first, then swap).
- No CI/CD pipeline — deploys are manual via rsync
- nginx TLS config is a commented-out block that gets replaced by setup-tls.sh (fragile)
- No health endpoint on backend (the /health route referenced in compose doesn't exist yet)
- docker-compose.prod.yml references `/opt/meeple/.env.prod` with absolute path
- No automated DB backups
- Manual ALTER TABLE migrations in main.py instead of proper Alembic migrations
- CORS is wide open (`allow_origins=["*"]`) — needs restricting for production
- Frontend Dockerfile doesn't use standalone output mode (larger image than needed)

## Design documents

The `docs/` directory contains comprehensive design specs. **Read these before major feature work:**

| Doc | Contents |
|-----|----------|
| `00-system-design.md` | Architecture, tech decisions, data model |
| `01-game-engine.md` | Plugin protocol, phase model, event sourcing |
| `02-backend-api.md` | REST + WebSocket API specs |
| `03-frontend.md` | Frontend architecture, components, state |
| `04-infra.md` | Docker, nginx, CI/CD, monitoring, scaling |
| `05-auth.md` | OIDC flow, JWT, account linking |
| `06-bot-api.md` | Bot integration (webhook + sandbox) |
| `07-replay-rankings.md` | Event sourcing replays, Glicko-2 rankings |
| `08-carcassonne.md` | Carcassonne implementation spec |

## Current status (Feb 2025)

### Done
- Core game engine with plugin protocol
- Carcassonne: full game logic, tiles, scoring, meeple placement
- Backend: FastAPI app, REST API, WebSocket game connection
- Auth: Google OIDC with JWT
- Frontend: lobby system, game UI with canvas rendering, responsive layout
- Infra: Docker Compose dev + prod, nginx, deploy scripts

### Not yet implemented
- CI/CD pipeline (GitHub Actions) — **priority**
- Proper Alembic migrations (currently using create_all + manual ALTER)
- Bot API (webhook + sandbox) — designed in doc 06
- Replay system — designed in doc 07
- Rankings/leaderboards (Glicko-2) — designed in doc 07
- Timer enforcement (designed but not enforced server-side)
- Additional OIDC providers (GitHub, Discord)
- Frontend tests
- Monitoring (Sentry, structured logging)
- DB backups
- Redis state cleanup for finished games

## Code conventions

- Backend: Python 3.12+, type hints everywhere, async/await for I/O
- Frontend: TypeScript strict mode, functional components, Tailwind for styling
- Game plugins must implement the `GamePlugin` protocol — see `engine/protocol.py`
- All env vars use `MEEPLE_` prefix on the backend
- API routes are versioned under `/api/v1/`
- WebSocket messages follow the schema in `ws/messages.py`
