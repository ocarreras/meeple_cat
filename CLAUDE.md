# CLAUDE.md — meeple.cat development guide

## What is this project?

meeple.cat is a board game platform where users play against humans or AI in real-time. It's designed as a plugin platform — adding a new game should only require game logic and UI components. First game: Carcassonne.

Domain: `play.meeple.cat`

## Monorepo structure

```
meeple/
├── backend/              Python (FastAPI) — REST API, WebSocket, game engine
├── frontend/             TypeScript (Next.js 16, React 19) — web client
├── infra/
│   ├── terraform/        Hetzner VPS + Route 53 DNS (IaC)
│   ├── k8s/meeple/       Helm chart (k8s manifests)
│   └── legacy/           Old Docker Compose deploy scripts (archived)
├── .github/workflows/    CI (pytest, tsc, lint) + CD (build, push, helm upgrade)
├── docs/                 Design documents (00-08) — READ THESE FIRST
└── docker-compose.yml    Local dev only (postgres + redis + backend + frontend)
```

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async), Pydantic 2 |
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

# Backend (from repo root)
cd backend
uv sync
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

# Specific test file
uv run pytest tests/games/carcassonne/test_scoring.py
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
| `04-infra.md` | Docker, nginx, CI/CD, monitoring, scaling |
| `05-auth.md` | OIDC flow, JWT, account linking |
| `06-bot-api.md` | Bot integration (webhook + sandbox) |
| `07-replay-rankings.md` | Event sourcing replays, Glicko-2 rankings |
| `08-carcassonne.md` | Carcassonne implementation spec |

## Current status (Feb 2025)

### Done
- Core game engine with plugin protocol
- Carcassonne: full game logic, tiles, scoring, meeple placement
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
- Frontend: TypeScript strict mode, functional components, Tailwind for styling
- Game plugins must implement the `GamePlugin` protocol — see `engine/protocol.py`
- All env vars use `MEEPLE_` prefix on the backend
- API routes are versioned under `/api/v1/`
- WebSocket messages follow the schema in `ws/messages.py`
