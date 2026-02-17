# CLAUDE.md — meeple.cat development guide

## What is this project?

meeple.cat is a board game platform where users play against humans or AI in real-time. It's designed as a plugin platform — adding a new game should only require game logic and UI components. First game: Carcassonne.

Domain: `play.meeple.cat`

## Monorepo structure

```
meeple/
├── backend/              Python (FastAPI) — REST API, WebSocket, game orchestration
├── game-engine/          Rust — game logic, MCTS bot AI (gRPC server)
├── frontend/             TypeScript (Next.js 16, React 19) — web client
├── infra/
│   ├── terraform/        Hetzner VPS + Route 53 DNS (IaC)
│   └── k8s/meeple/       Helm chart (k8s manifests)
├── .github/workflows/    CI (pytest, tsc, lint) + CD (build, push, helm upgrade)
├── docs/                 Design documents (00-09) — READ THESE FIRST
└── docker-compose.yml    Local dev (postgres + redis + backend + game-engine + frontend)
```

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async), Pydantic 2 |
| Game Engine | Rust, tonic (gRPC), rayon (parallelism) — game logic + MCTS |
| Database | PostgreSQL 16, Redis 7 |
| Frontend | Next.js 16 (App Router, standalone output), React 19, TypeScript 5, Tailwind 4, Zustand 5 |
| Auth | Google OIDC → JWT (HttpOnly cookies) |
| Package mgmt | uv (backend), npm (frontend) |
| Infra | k3s on Hetzner CX32, Traefik ingress, cert-manager (Let's Encrypt) |
| IaC | Terraform (Hetzner + Route 53), Helm chart |
| CI/CD | GitHub Actions → GHCR → helm upgrade |

## Local development

```bash
# Start postgres + redis
docker compose up -d postgres redis

# Rust game engine (from repo root)
cd game-engine
cargo run --release
# Listens on localhost:50051

# Backend (from repo root)
cd backend
uv sync
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (from repo root)
cd frontend
npm install
npm run dev
```

Backend runs on http://localhost:8000, game engine on gRPC localhost:50051, frontend on http://localhost:3000.

The backend connects to the Rust game engine at startup (configured via `MEEPLE_GAME_ENGINE_GRPC_URL`, default `localhost:50051`). It will retry connection up to 30 times with 2s delay.

All backend settings use `MEEPLE_` env prefix (see `backend/src/config.py`).

## Backend architecture

### Game engine (the heart of the platform)

Game logic runs in a dedicated **Rust engine** (`game-engine/`) that communicates with the Python backend via **gRPC**. The Python backend handles orchestration (session management, event sourcing, WebSocket broadcasting), while all game rules and MCTS AI run in Rust for performance.

**Python orchestration layer** (`backend/src/engine/`):
- **`protocol.py`** — `GamePlugin` protocol (type contract)
- **`grpc_plugin.py`** — `GrpcGamePlugin` adapter that translates protocol calls to gRPC
- **`session.py`** — `GameSession` orchestrates a single active game
- **`session_manager.py`** — manages all active sessions, handles recovery
- **`state_store.py`** — Redis for hot game state
- **`event_store.py`** — Postgres append-only event log
- **`registry.py`** — discovers games from Rust engine via `ListGames` gRPC call
- **`bot_runner.py`** / **`bot_strategy.py`** — built-in bot execution (MCTS via gRPC)

Key flow: client sends action via WebSocket → `GameSession.handle_action()` validates envelope → delegates to Rust via gRPC for rule validation and state transition → persists events to Postgres → updates state in Redis → broadcasts `PlayerView` to all connected clients.

### Game plugins (Rust)

Games are implemented in `game-engine/src/games/<game_name>/` using the `TypedGamePlugin` Rust trait. The Python backend discovers games automatically via gRPC at startup — no Python code changes needed to add a new game.

Currently implemented: **Carcassonne** (`game-engine/src/games/carcassonne/`)
- `plugin.rs` — main plugin implementing `TypedGamePlugin`
- `tiles.rs` — 72 tile definitions
- `board.rs` — board representation and placement validation
- `features.rs` — feature tracking and merging (cities, roads, fields, monasteries)
- `scoring.rs` — in-game and end-game scoring
- `meeples.rs` — meeple placement validation
- `evaluator.rs` — heuristic evaluation for MCTS

### API structure

REST under `/api/v1/`:
- `api/auth.py` — token refresh, /me endpoint
- `api/games.py` — game catalog
- `api/rooms.py` — lobby CRUD, join, start
- `api/matches.py` — match state, events
- `api/users.py` — user profiles
- `api/health.py` — `/health` (liveness) and `/ready` (readiness, checks DB + Redis)

Auth (OIDC): `auth/routes.py`, `auth/jwt.py`, `auth/providers.py`

WebSocket: `ws/handler.py` at `/ws/game/{match_id}` — uses ticket-based auth

### Database

- Models in `backend/src/models/` (user, room, match, base, database)
- Auth models in `backend/src/auth/models.py` (UserAuth for multi-provider support)
- Tables are created via `Base.metadata.create_all` in main.py lifespan (NOT Alembic yet for schema creation)
- Manual ALTER TABLE migrations in `main.py` lifespan — this is tech debt

### Graceful shutdown

On SIGTERM (k8s rolling update), the backend:
1. Sends WebSocket close frame (code 1001) to all connected players/spectators
2. Frontend auto-reconnects with exponential backoff (`useWebSocket.ts`)
3. Closes Redis and DB connections
4. `terminationGracePeriodSeconds: 30` in the Deployment gives time for drain

Game state persists in Redis. On startup, `session_manager.recover_sessions()` reloads active matches. Clients reconnect and receive current game state immediately.

## Frontend architecture

- Next.js App Router with `output: "standalone"` for optimized Docker images
- Key pages: `/` (landing), `/login`, `/lobby` (room list), `/lobby/[roomId]` (room), `/game/[matchId]` (active game), `/profile/[userId]`
- Game UI uses canvas rendering (`components/game/BoardCanvas.tsx`)
- Carcassonne-specific components in `components/games/carcassonne/`
- API client in `lib/api.ts`, types in `lib/types.ts`
- Auth state managed via `AuthInitializer.tsx` component
- WebSocket reconnection with exponential backoff in `hooks/useWebSocket.ts`

## Running tests

```bash
# Backend tests (from backend/)
uv run pytest

# Backend tests with verbose output
uv run pytest -v

# Rust game engine tests (from game-engine/)
cargo test --release

# Quick Rust tests (skip slow arena tests)
cargo test --release --lib -- --skip arena --skip mcts_per_game
```

No frontend tests yet.

## Infrastructure

### Overview

- **VPS**: Hetzner CX32 (4 vCPU, 8GB RAM, ~$12/mo) running k3s
- **Ingress**: Traefik (bundled with k3s) — handles routing, WebSocket upgrade, TLS termination
- **TLS**: cert-manager with Let's Encrypt (automatic provisioning and renewal)
- **DNS**: AWS Route 53 (A record → Hetzner IP)
- **Container registry**: GitHub Container Registry (GHCR)
- **Secrets**: Kubernetes Secrets, populated via Helm values-prod.yaml (gitignored)
- **DB backups**: CronJob running pg_dump daily at 3 AM, 7-day retention

### Terraform (infra/terraform/)

Provisions the Hetzner VPS with k3s + cert-manager + Helm, and creates the Route 53 DNS record.

```bash
cd infra/terraform
ssh-keygen -t ed25519 -f ~/.ssh/meeple-hetzner -N ""
cp terraform.tfvars.example terraform.tfvars  # fill in hcloud_token
terraform init
terraform plan
terraform apply

# Fetch kubeconfig
scp root@<IP>:/etc/rancher/k3s/k3s.yaml ~/.kube/meeple-config
# Edit: replace 127.0.0.1 with server IP
export KUBECONFIG=~/.kube/meeple-config
kubectl get nodes
```

### Helm chart (infra/k8s/meeple/)

Deploys all application components to k3s.

```bash
# Validate templates locally
helm template meeple ./infra/k8s/meeple

# Manual deploy (CI/CD does this automatically)
helm upgrade --install meeple ./infra/k8s/meeple \
  --namespace meeple --create-namespace \
  -f ./infra/k8s/meeple/values.yaml \
  -f ./infra/k8s/meeple/values-prod.yaml \
  --wait
```

Components deployed:
- Backend Deployment (rolling update, `maxUnavailable: 0`, readiness/liveness probes)
- Game Engine Deployment (Rust gRPC server on port 50051)
- Frontend Deployment (rolling update, standalone Next.js)
- PostgreSQL StatefulSet (10Gi PVC)
- Redis Deployment (256MB maxmemory, allkeys-lru)
- Traefik Ingress (routes /api/\*, /ws/\* → backend, /\* → frontend)
- ClusterIssuer (Let's Encrypt)
- CronJob (daily pg_dump backup)

### CI/CD (.github/workflows/)

**On PR to main** (`ci.yml`): runs pytest, tsc --noEmit, eslint

**On push to main** (`deploy.yml`):
1. Runs tests
2. Builds Docker images → pushes to GHCR (tagged with git SHA)
3. `helm upgrade` on k3s cluster with new image tags
4. Verifies rollout status

**GitHub repo secrets needed:**
| Secret | Description |
|--------|-------------|
| `KUBECONFIG_DATA` | Base64-encoded k3s kubeconfig |
| `HELM_VALUES_PROD` | Base64-encoded values-prod.yaml |

### Known remaining infra issues

- Manual ALTER TABLE migrations in main.py instead of proper Alembic migrations
- Single-node k3s — no HA (acceptable for hobby project)
- DB backups stored on same server (no offsite backup yet)
- k8s API port (6443) open to all IPs — should restrict to your IP

## Design documents

The `docs/` directory contains comprehensive design specs. **Read these before major feature work:**

| Doc | Contents |
|-----|----------|
| `00-system-design.md` | Architecture, tech decisions, data model |
| `01-game-engine.md` | Plugin protocol, phase model, event sourcing |
| `02-backend-api.md` | REST + WebSocket API specs |
| `03-frontend.md` | Frontend architecture, components, state |
| `04-infra.md` | Infrastructure design (historical — actual setup is k3s/Terraform/Helm, see above) |
| `05-auth.md` | OIDC flow, JWT, account linking |
| `06-bot-api.md` | Bot integration (webhook + sandbox) — design spec, not yet implemented |
| `07-replay-rankings.md` | Event sourcing replays, Glicko-2 rankings |
| `08-carcassonne.md` | Carcassonne implementation spec (canonical impl now in Rust) |
| `09-rust-mcts-engine.md` | Rust game engine architecture, MCTS, performance benchmarks |

## Current status (Feb 2025)

### Done
- Core game engine with plugin protocol (Python orchestration + Rust game logic via gRPC)
- Rust game engine: all game logic, MCTS bot AI (~20x faster than Python)
- Carcassonne: full game logic, tiles, scoring, meeple placement (Rust)
- Built-in bots: Random + MCTS (Rust) with progressive widening, RAVE
- Backend: FastAPI app, REST API, WebSocket game connection, health endpoints
- Auth: Google OIDC with JWT
- Frontend: lobby system, game UI with canvas rendering, responsive layout
- Infra: k3s on Hetzner, Terraform IaC, Helm chart, GitHub Actions CI/CD
- Zero-downtime rolling deployments
- Automatic TLS via cert-manager
- Automated daily PostgreSQL backups
- Graceful WebSocket shutdown + client auto-reconnection

### Not yet implemented
- Proper Alembic migrations (currently using create_all + manual ALTER)
- Bot API (webhook + sandbox) — designed in doc 06
- Replay system — designed in doc 07
- Rankings/leaderboards (Glicko-2) — designed in doc 07
- Timer enforcement (designed but not enforced server-side)
- Additional OIDC providers (GitHub, Discord)
- Frontend tests
- Monitoring (Sentry, structured logging)
- Redis state cleanup for finished games
- Offsite DB backups

## Code conventions

- Backend: Python 3.12+, type hints everywhere, async/await for I/O
- Game engine: Rust, typed game plugins via `TypedGamePlugin` trait
- Frontend: TypeScript strict mode, functional components, Tailwind for styling
- Game plugins implement the `TypedGamePlugin` trait in Rust — see `game-engine/src/engine/plugin.rs`
- All env vars use `MEEPLE_` prefix on the backend
- API routes are versioned under `/api/v1/`
- WebSocket messages follow the schema in `ws/messages.py`
