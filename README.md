# meeple.cat

A board game platform where you play against humans or AI in real-time. Built as a plugin system — adding a new game requires only game logic and UI components, not infrastructure changes.

**First game: Carcassonne.**

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌──────────────┐
│  Next.js    │    │  FastAPI    │    │  PostgreSQL  │
│  (React 19) │◄──►│  (Python)   │◄──►│  + Redis     │
│  Frontend   │ WS │  Backend    │    │              │
└─────────────┘    └──────┬──────┘    └──────────────┘
                          │ gRPC
                   ┌──────┴──────┐
                   │ Rust Game   │
                   │ Engine      │
                   └─────────────┘
```

- **Backend**: Python 3.12, FastAPI, SQLAlchemy (async), Pydantic — orchestration, API, WebSocket
- **Game Engine**: Rust, tonic (gRPC), rayon — game logic, MCTS bot AI
- **Frontend**: Next.js 16 (App Router), TypeScript, Tailwind CSS, Zustand
- **Database**: PostgreSQL 16 (persistent data) + Redis 7 (hot game state, sessions)
- **Auth**: Google OIDC → JWT
- **Real-time**: WebSocket for game communication
- **Infra**: k3s on Hetzner, Terraform, Helm, GitHub Actions CI/CD

## Game engine

The platform uses a **plugin-based game engine** where each game implements the `TypedGamePlugin` trait in Rust. The Python backend communicates with the Rust engine via gRPC, using a `GrpcGamePlugin` adapter that implements the `GamePlugin` protocol:

```python
class GamePlugin(Protocol):
    def create_initial_state(self, players, config) -> GameState
    def validate_action(self, state, action) -> list[str]
    def apply_action(self, state, action) -> TransitionResult
    def get_player_view(self, state, player_id) -> PlayerView
    def get_valid_actions(self, state, player_id) -> list[Action]
```

Games are phase-based state machines with event sourcing. The server is authoritative — it validates all actions, filters hidden information per player, and broadcasts updates via WebSocket.

Game plugins are implemented in Rust (`game-engine/src/games/`) and discovered via gRPC at startup.

## Quick start

### Prerequisites

- Docker and Docker Compose
- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js 20+

### Run locally

```bash
# Start database services
docker compose up -d postgres redis

# Rust game engine (in a terminal)
cd game-engine
cargo run --release

# Backend (in another terminal)
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
| `MEEPLE_GAME_ENGINE_GRPC_URL` | `localhost:50051` | Rust game engine gRPC address |

## Project structure

```
meeple/
├── backend/
│   ├── src/
│   │   ├── main.py              # FastAPI app, lifespan
│   │   ├── config.py            # Settings (MEEPLE_ env vars)
│   │   ├── api/                 # REST endpoints (auth, games, rooms, matches, users)
│   │   ├── auth/                # OIDC login, JWT, cookie handling
│   │   ├── engine/              # Game orchestration
│   │   │   ├── protocol.py      # GamePlugin interface (type contract)
│   │   │   ├── grpc_plugin.py   # GrpcGamePlugin adapter (delegates to Rust)
│   │   │   ├── session.py       # Single game session
│   │   │   ├── session_manager.py
│   │   │   ├── bot_runner.py    # Bot move scheduling
│   │   │   ├── bot_strategy.py  # Bot strategies (Random, MCTS via gRPC)
│   │   │   ├── state_store.py   # Redis state persistence
│   │   │   └── event_store.py   # Postgres event log
│   │   ├── models/              # SQLAlchemy models
│   │   └── ws/                  # WebSocket handler, broadcaster
│   └── tests/
├── game-engine/                 # Rust game engine (gRPC server)
│   └── src/
│       ├── engine/              # MCTS, arena, simulator, plugin trait
│       ├── games/               # Game implementations (carcassonne, tictactoe)
│       └── server.rs            # gRPC server (tonic)
├── frontend/
│   ├── src/
│   │   ├── app/                 # Next.js pages (lobby, game, login, profile)
│   │   ├── components/          # UI components (game canvas, lobby, carcassonne)
│   │   └── lib/                 # API client, types, game assets
│   └── public/
├── infra/
│   ├── terraform/               # Hetzner VPS + Route 53 DNS (IaC)
│   └── k8s/meeple/              # Helm chart for k3s deployment
├── .github/workflows/           # CI + CD pipelines
├── docs/                        # Design documents (10 files, ~150KB)
└── docker-compose.yml           # Local development
```

## Tests

```bash
# Backend (Python)
cd backend
uv run pytest          # all tests
uv run pytest -v       # verbose

# Game engine (Rust)
cd game-engine
cargo test --release   # full suite (~3 min)
```

## Deployment

Production runs on k3s (lightweight Kubernetes) on a Hetzner CX32 VPS. Infrastructure is defined as code with Terraform, app manifests as a Helm chart, and CI/CD via GitHub Actions.

Pushing to `main` automatically: runs tests, builds Docker images, pushes to GHCR, and deploys via `helm upgrade` with zero-downtime rolling updates.

```bash
# First-time infra provisioning
cd infra/terraform
terraform init && terraform apply

# Manual Helm deploy (CI/CD does this automatically)
helm upgrade --install meeple ./infra/k8s/meeple \
  --namespace meeple --create-namespace \
  -f ./infra/k8s/meeple/values.yaml \
  -f ./infra/k8s/meeple/values-prod.yaml
```

See `CLAUDE.md` for detailed infrastructure documentation.

## Design documentation

The `docs/` directory contains comprehensive design documents covering every subsystem:

| # | Document | Description |
|---|----------|-------------|
| 00 | System Design | Architecture, tech decisions, data model |
| 01 | Game Engine | Plugin protocol, phase model, event sourcing |
| 02 | Backend API | REST + WebSocket API specification |
| 03 | Frontend | UI architecture, components, state management |
| 04 | Infrastructure | Infrastructure design (historical — actual setup is k3s/Terraform/Helm) |
| 05 | Auth | OIDC flow, JWT, account linking |
| 06 | Bot API | AI/bot integration (webhook + sandbox) |
| 07 | Replay & Rankings | Event sourcing replays, Glicko-2 ratings |
| 08 | Carcassonne | Complete game implementation spec (canonical impl now in Rust) |
| 09 | Rust MCTS Engine | Rust game engine architecture, performance benchmarks |

## License

Private project.
