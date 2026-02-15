# meeple.cat

A board game platform where you play against humans or AI in real-time. Built as a plugin system — adding a new game requires only game logic and UI components, not infrastructure changes.

**First game: Carcassonne.**

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌──────────────┐
│  Next.js    │    │  FastAPI     │    │  PostgreSQL   │
│  (React 19) │◄──►│  (Python)   │◄──►│  + Redis      │
│  Frontend   │ WS │  Backend    │    │               │
└─────────────┘    └─────────────┘    └──────────────┘
```

- **Backend**: Python 3.12, FastAPI, SQLAlchemy (async), Pydantic
- **Frontend**: Next.js 16 (App Router), TypeScript, Tailwind CSS, Zustand
- **Database**: PostgreSQL 16 (persistent data) + Redis 7 (hot game state, sessions)
- **Auth**: Google OIDC → JWT
- **Real-time**: WebSocket for game communication
- **Infra**: Docker Compose on AWS EC2

## Game engine

The platform uses a **plugin-based game engine** where each game implements a standard protocol:

```python
class GamePlugin(Protocol):
    def create_initial_state(self, players, config) -> GameState
    def validate_action(self, state, action) -> list[str]
    def apply_action(self, state, action) -> TransitionResult
    def get_player_view(self, state, player_id) -> PlayerView
    def get_valid_actions(self, state, player_id) -> list[Action]
```

Games are phase-based state machines with event sourcing. The server is authoritative — it validates all actions, filters hidden information per player, and broadcasts updates via WebSocket.

Game plugins live in `backend/src/games/` and are auto-discovered at startup.

## Quick start

### Prerequisites

- Docker and Docker Compose
- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js 20+

### Run locally

```bash
# Start database services
docker compose up -d postgres redis

# Backend
cd backend
uv sync
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (in another terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:3000.

### Run everything in Docker

```bash
docker compose up --build
```

### Configuration

Backend configuration uses `MEEPLE_` prefixed environment variables. Copy the example env file:

```bash
cp backend/.env.example backend/.env
```

Key settings:
| Variable | Default | Description |
|----------|---------|-------------|
| `MEEPLE_DATABASE_URL` | `postgresql+asyncpg://meeple:meeple_dev@localhost:5432/meeple` | PostgreSQL connection |
| `MEEPLE_REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `MEEPLE_JWT_SECRET` | `dev-secret-change-in-production` | JWT signing key |
| `MEEPLE_GOOGLE_CLIENT_ID` | *(empty)* | Google OIDC client ID |
| `MEEPLE_GOOGLE_CLIENT_SECRET` | *(empty)* | Google OIDC client secret |
| `MEEPLE_FRONTEND_URL` | `http://localhost:3000` | Frontend URL for CORS/redirects |
| `MEEPLE_BASE_URL` | `http://localhost:8000` | Backend public URL |

## Project structure

```
meeple/
├── backend/
│   ├── src/
│   │   ├── main.py              # FastAPI app, lifespan
│   │   ├── config.py            # Settings (MEEPLE_ env vars)
│   │   ├── api/                 # REST endpoints (auth, games, rooms, matches, users)
│   │   ├── auth/                # OIDC login, JWT, cookie handling
│   │   ├── engine/              # Core game engine
│   │   │   ├── protocol.py      # GamePlugin interface
│   │   │   ├── session.py       # Single game session
│   │   │   ├── session_manager.py
│   │   │   ├── state_store.py   # Redis state persistence
│   │   │   └── event_store.py   # Postgres event log
│   │   ├── games/
│   │   │   └── carcassonne/     # Carcassonne plugin (tiles, board, scoring, meeples)
│   │   ├── models/              # SQLAlchemy models
│   │   └── ws/                  # WebSocket handler, broadcaster
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── app/                 # Next.js pages (lobby, game, login, profile)
│   │   ├── components/          # UI components (game canvas, lobby, carcassonne)
│   │   └── lib/                 # API client, types, game assets
│   └── public/
├── infra/                       # nginx config, deploy scripts, env templates
├── docs/                        # Design documents (9 files, ~150KB)
├── docker-compose.yml           # Local development
└── docker-compose.prod.yml      # Production deployment
```

## Tests

```bash
cd backend
uv run pytest          # all tests
uv run pytest -v       # verbose
uv run pytest tests/games/carcassonne/  # carcassonne tests only
```

## Deployment

Production runs on a single AWS EC2 instance (t3.medium) with Docker Compose, nginx as reverse proxy, and Let's Encrypt TLS.

```bash
# Deploy code updates
./infra/deploy-update.sh all

# First-time provisioning
DOMAIN=play.meeple.cat ./infra/aws-deploy.sh
```

See `docs/04-infra.md` for full infrastructure documentation.

## Design documentation

The `docs/` directory contains comprehensive design documents covering every subsystem:

| # | Document | Description |
|---|----------|-------------|
| 00 | System Design | Architecture, tech decisions, data model |
| 01 | Game Engine | Plugin protocol, phase model, event sourcing |
| 02 | Backend API | REST + WebSocket API specification |
| 03 | Frontend | UI architecture, components, state management |
| 04 | Infrastructure | Docker, nginx, CI/CD, monitoring, scaling |
| 05 | Auth | OIDC flow, JWT, account linking |
| 06 | Bot API | AI/bot integration (webhook + sandbox) |
| 07 | Replay & Rankings | Event sourcing replays, Glicko-2 ratings |
| 08 | Carcassonne | Complete game implementation spec |

## License

Private project.
