# meeple.cat — System Design v1

## Vision

A board game platform where users play against other humans or AI in real-time.
Designed as a plugin platform — adding a new game should require only game logic
and UI components, not infrastructure changes.

First game: **Carcassonne**.

---

## Decision Log

| Domain | Decision |
|---|---|
| Backend | Python (FastAPI) |
| Frontend | TypeScript (Next.js / React) |
| Real-time | WebSocket (direct, no broker) |
| Hosting | Self-hosted VPS (Docker Compose) |
| DB | PostgreSQL (persistent) + Redis (hot state, pub/sub) |
| Auth | OpenID Connect — Google, GitHub, Discord |
| Game authority | Server-authoritative |
| Hidden info | Server filters per-player views |
| Turn model | Phase-based with action queues |
| Concurrent play | Commit-reveal + time-window (game-configurable) |
| Replays | Event sourcing (action log) |
| AI interface | External webhook bots + sandboxed uploaded bots |
| Frontend UX | Desktop-first, mobile-friendly |
| Game UI | Hybrid: reusable primitives + game-specific components |
| Repo | Monorepo |
| Cost target | < $100/month |

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                          CLIENTS                                 │
│  Next.js Web App          Mobile (future)        Bot Clients     │
│  (React + WebSocket)      (React Native)         (HTTP API)      │
└──────────┬───────────────────┬──────────────────────┬────────────┘
           │ HTTPS / WSS       │                      │ HTTPS
           ▼                   ▼                      ▼
┌──────────────────────────────────────────────────────────────────┐
│                     NGINX (reverse proxy + TLS)                  │
└──────────┬───────────────────┬──────────────────────┬────────────┘
           │                   │                      │
           ▼                   ▼                      ▼
┌─────────────────┐  ┌─────────────────┐  ┌────────────────────┐
│   Next.js SSR   │  │  Game Server    │  │   Bot API Gateway  │
│   (frontend)    │  │  (FastAPI +     │  │   (FastAPI)        │
│                 │  │   WebSocket)    │  │                    │
└─────────────────┘  └────────┬────────┘  └────────┬───────────┘
                              │                     │
                    ┌─────────┴─────────┐           │
                    ▼                   ▼           ▼
              ┌──────────┐      ┌────────────┐  ┌──────────────┐
              │PostgreSQL│      │   Redis     │  │  Sandboxed   │
              │          │      │(game state, │  │  Bot Runner  │
              │ users    │      │ sessions,   │  │  (future)    │
              │ games    │      │ pub/sub)    │  │              │
              │ events   │      │             │  │              │
              │ rankings │      │             │  │              │
              └──────────┘      └─────────────┘  └──────────────┘
```

---

## Monorepo Structure

```
meeple/
├── docs/                      # Architecture & design docs
│   ├── 00-system-design.md    # This file
│   ├── 01-game-engine.md      # Game abstraction deep-dive
│   ├── 02-backend-api.md      # REST + WebSocket API design
│   ├── 03-frontend.md         # Frontend architecture
│   ├── 04-infra.md            # Docker, deploy, monitoring
│   ├── 05-auth.md             # Auth system design
│   ├── 06-bot-api.md          # AI/Bot integration API
│   ├── 07-replay-rankings.md  # Replay & ranking systems
│   └── 08-carcassonne.md      # First game implementation
├── backend/
│   ├── pyproject.toml
│   ├── src/
│   │   ├── main.py            # FastAPI app entry point
│   │   ├── auth/              # OIDC auth module
│   │   ├── api/               # REST endpoints
│   │   ├── ws/                # WebSocket handlers
│   │   ├── engine/            # Core game engine (abstract)
│   │   ├── games/             # Game plugin implementations
│   │   │   └── carcassonne/
│   │   ├── bot/               # Bot API gateway + sandbox
│   │   ├── matchmaking/       # Lobby, matchmaking, timers
│   │   ├── replay/            # Event sourcing & replay
│   │   ├── ranking/           # ELO / ranking system
│   │   └── models/            # SQLAlchemy / Pydantic models
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── app/               # Next.js app router
│   │   ├── components/
│   │   │   ├── ui/            # Generic primitives (grid, hand, dice, tokens)
│   │   │   └── games/         # Game-specific UI components
│   │   │       └── carcassonne/
│   │   ├── hooks/             # React hooks (useWebSocket, useGameState, etc.)
│   │   ├── lib/               # Utilities, API client
│   │   └── stores/            # Client state (zustand or similar)
│   └── tests/
├── shared/                    # Shared type definitions
│   └── types/                 # TypeScript types generated from Python models
├── infra/
│   ├── docker-compose.yml
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── nginx/
└── scripts/                   # Dev tooling, DB migrations, etc.
```

---

## Core Subsystems

### 1. Game Engine (the heart of the platform)

The game engine is the abstract framework that all games plug into. It must be
generic enough to model turn-based, phase-based, and simultaneous-play games.

#### Core Concepts

```
GameDefinition          — Static rules, metadata, constraints for a game type
GameState               — Complete state of a game in progress
PlayerView              — Filtered state visible to a specific player
Phase                   — A named stage in the game flow (e.g., "place_tile", "score")
Action                  — A player's input (validated against current phase)
ActionQueue             — Ordered list of expected/pending actions in a phase
Event                   — Immutable record of what happened (for replay)
TransitionResult        — New state + events + next expected actions
```

#### The Game Plugin Interface

Every game must implement this interface:

```python
class GamePlugin(Protocol):
    """Interface that every game must implement."""

    # --- Metadata ---
    game_id: str                           # e.g. "carcassonne"
    display_name: str                      # e.g. "Carcassonne"
    min_players: int
    max_players: int

    # --- Lifecycle ---
    def create_initial_state(self, players: list[Player], config: GameConfig) -> GameState:
        """Generate the starting state (shuffle tiles, deal cards, etc.)."""
        ...

    def get_current_phase(self, state: GameState) -> Phase:
        """Return the current phase of the game."""
        ...

    def get_valid_actions(self, state: GameState, player_id: str) -> list[Action]:
        """Return all legal actions for a player in the current state."""
        ...

    def apply_action(self, state: GameState, action: Action) -> TransitionResult:
        """
        Apply an action to the state. Returns:
        - new_state: the updated game state
        - events: list of events that occurred (for replay log)
        - next_actions: what actions are expected next (who plays, what kind)

        This is the core state machine transition.
        """
        ...

    def get_player_view(self, state: GameState, player_id: str) -> PlayerView:
        """Filter state to only what this player is allowed to see."""
        ...

    def is_game_over(self, state: GameState) -> GameResult | None:
        """Return result if game is over, None otherwise."""
        ...

    # --- Concurrent play support ---
    def get_concurrent_action_mode(self, state: GameState) -> ConcurrentMode:
        """Return SEQUENTIAL, COMMIT_REVEAL, or TIME_WINDOW for current phase."""
        ...

    def resolve_concurrent_actions(
        self, state: GameState, actions: dict[str, Action]
    ) -> TransitionResult:
        """Resolve simultaneously submitted actions."""
        ...

    # --- AI interface ---
    def state_to_ai_prompt(self, state: GameState, player_id: str) -> dict:
        """
        Serialize state into the format the AI API expects.
        Same filtered view as get_player_view but optimized for machine consumption.
        """
        ...

    def action_from_ai_response(self, response: dict) -> Action:
        """Parse an AI's response into a valid Action."""
        ...
```

#### Phase & Action Queue Model

```
Game flow = sequence of Phases
Phase    = { name, action_queue, concurrent_mode, auto_advance }
ActionQueue = ordered list of ExpectedAction
ExpectedAction = { player_id | ALL, action_type, constraints, timeout }

Example — Caylus turn:
  Phase("place_workers")    → sequential, one action per player per round
  Phase("activate_buildings") → sequential, resolve in board order
  Phase("build_castle")     → sequential, current player chooses
  Phase("king_movement")    → automatic (no player input)

Example — 7 Wonders card selection:
  Phase("choose_card")      → COMMIT_REVEAL, all players simultaneously
  Phase("resolve_cards")    → automatic
```

#### Event Sourcing

Every `apply_action` call produces `Event` objects:

```python
@dataclass
class Event:
    event_id: str           # UUID
    game_id: str
    sequence_number: int    # Monotonically increasing
    timestamp: datetime
    event_type: str         # "tile_placed", "meeple_placed", "score_updated"
    player_id: str | None   # None for system events
    payload: dict           # Game-specific data

    # Derived from action but may differ (action = intent, event = what happened)
```

Replaying a game: `initial_state → apply events in sequence → any point in game`

---

### 2. Game Server (WebSocket Real-Time)

The game server manages active game sessions via WebSocket.

#### Connection Flow

```
1. Client authenticates via REST (gets JWT)
2. Client opens WebSocket to /ws/game/{game_id}?token={jwt}
3. Server validates token, associates connection with player
4. Server sends current PlayerView
5. Bidirectional messages:
   Client → Server: { type: "action", payload: {...} }
   Server → Client: { type: "state_update", view: {...} }
   Server → Client: { type: "action_required", expected: {...} }
   Server → Client: { type: "timer_update", remaining_ms: ... }
   Server → Client: { type: "game_over", result: {...} }
```

#### Active Game Lifecycle

```
Redis holds:
  game:{id}:state     → serialized GameState (hot, fast access)
  game:{id}:timers    → per-player remaining time
  game:{id}:connections → set of connected player WebSocket IDs

PostgreSQL holds:
  games table          → game metadata, status, players, config
  game_events table    → append-only event log (event sourcing)

Flow:
  1. Game created → initial state in Redis + Postgres
  2. Each action → validate → apply → new state to Redis + event to Postgres
  3. Game over → final state to Postgres, clean up Redis
```

---

### 3. Timer System

Timers are critical for real-time play. The system supports multiple timing modes,
configurable per game:

```python
class TimerMode(Enum):
    FISCHER = "fischer"           # Base time + increment per turn
    BYOYOMI = "byoyomi"          # Main time + N byo-yomi periods
    SIMPLE = "simple"            # Fixed time per turn, no accumulation
    TOTAL = "total"              # Total time for the whole game (chess clock)

class TimeoutBehavior(Enum):
    LOSE_GAME = "lose_game"
    LOSE_TURN = "lose_turn"
    RANDOM_ACTION = "random_action"
    FORCE_PASS = "force_pass"

@dataclass
class TimerConfig:
    mode: TimerMode
    base_time_ms: int
    increment_ms: int = 0        # For Fischer
    timeout_behavior: TimeoutBehavior = TimeoutBehavior.LOSE_TURN
```

Timer ticks are managed server-side (Redis TTL keys or periodic tasks).
Clients receive `timer_update` messages for display.

---

### 4. AI / Bot API

The AI interface is uniform regardless of whether the bot is:
- Built-in (runs on the server)
- External webhook (user-hosted)
- Sandboxed uploaded code (future)

#### Bot API Contract

The platform calls the bot with:

```
POST /move
Content-Type: application/json

{
  "game_id": "carcassonne",
  "match_id": "uuid",
  "player_id": "bot-123",
  "state": { ... },              // PlayerView (filtered, same as human sees)
  "valid_actions": [ ... ],       // List of legal actions
  "phase": "place_tile",
  "time_remaining_ms": 30000,
  "metadata": {
    "turn_number": 12,
    "scores": { ... },
    "players": [ ... ]
  }
}
```

The bot responds with:

```
{
  "action": {
    "type": "place_tile",
    "payload": { "x": 3, "y": -1, "rotation": 90 }
  },
  "metadata": {                   // Optional, for debugging/display
    "confidence": 0.85,
    "thinking_time_ms": 450
  }
}
```

#### Bot Registration

```
POST /api/bots
{
  "name": "My Carcassonne Bot",
  "game_id": "carcassonne",
  "type": "webhook",              // or "uploaded"
  "webhook_url": "https://my-bot.example.com/move",
  "auth_header": "Bearer xxx"     // Optional auth for webhook
}
```

---

### 5. Auth System

OpenID Connect with Google, GitHub, Discord.

```
Flow:
  1. Client redirects to /auth/{provider}/login
  2. Server redirects to provider's OIDC authorize endpoint
  3. Provider redirects back to /auth/{provider}/callback
  4. Server exchanges code for tokens, extracts user info
  5. Server creates/updates user record in Postgres
  6. Server issues JWT (short-lived access + longer-lived refresh)
  7. Client stores JWT, uses for REST + WebSocket auth
```

User model is minimal — users can play immediately:

```python
@dataclass
class User:
    id: str                     # UUID
    provider: str               # "google" | "github" | "discord"
    provider_id: str            # ID from the provider
    email: str | None
    display_name: str           # Defaults from provider, user can change
    avatar_url: str | None
    created_at: datetime
    last_seen_at: datetime
    # Profile fields (all optional, filled later)
    bio: str | None
    country: str | None
```

---

### 6. Matchmaking & Lobby

```
Lobby:
  - User creates a game room (picks game, player count, timer config, AI slots)
  - Room appears in lobby list
  - Other users join
  - Creator starts game when ready

Matchmaking (future iteration):
  - User queues for a game type + rating range
  - Server matches players automatically

Quick play:
  - User clicks "Play vs AI" → instant game, no lobby needed
```

---

### 7. Ranking System

Per-game ELO (or Glicko-2) ratings:

```python
@dataclass
class PlayerRating:
    user_id: str
    game_id: str                # Rating is per-game
    rating: float               # e.g. 1500.0
    deviation: float            # Uncertainty (Glicko-2)
    volatility: float           # Glicko-2
    games_played: int
    last_played: datetime
```

Rankings computed after each game ends. Leaderboards are materialized views
or cached queries in Postgres.

---

### 8. Replay System

Built on top of event sourcing:

```
GET /api/games/{match_id}/replay

Returns:
{
  "game_id": "carcassonne",
  "players": [...],
  "initial_state": { ... },     // Public view of starting state
  "events": [                   // Ordered event log
    { "seq": 1, "type": "tile_drawn", ... },
    { "seq": 2, "type": "tile_placed", ... },
    ...
  ],
  "result": { "winner": "player-1", "scores": {...} }
}
```

Frontend replayer: step forward/backward through events, reconstruct state
at any point. Since game logic is deterministic, the client can replay locally
using the same `apply_action` logic (shared via WASM or reimplemented in TS).

---

## Data Model (PostgreSQL)

```sql
-- Users
users (id, provider, provider_id, email, display_name, avatar_url, bio, country, created_at, last_seen_at)

-- Games catalog (static, seeded)
game_definitions (game_id PK, display_name, min_players, max_players, description, config_schema JSONB)

-- Matches (game instances)
matches (id, game_id FK, status, config JSONB, created_by FK, created_at, started_at, ended_at)
match_players (match_id FK, user_id FK, seat_index, is_bot, bot_id, result, score)

-- Event sourcing
game_events (id, match_id FK, sequence_number, event_type, player_id, payload JSONB, timestamp)
  -- Index on (match_id, sequence_number) for replay
  -- Append-only, never updated

-- Rankings
player_ratings (user_id FK, game_id FK, rating, deviation, volatility, games_played, last_played)
  -- PK on (user_id, game_id)

-- Bots
bots (id, owner_id FK, name, game_id FK, type, webhook_url, config JSONB, created_at, is_active)

-- Lobby
game_rooms (id, game_id FK, created_by FK, config JSONB, status, max_players, created_at)
game_room_seats (room_id FK, seat_index, user_id FK, is_bot, bot_id, is_ready)
```

---

## Infrastructure (Docker Compose on VPS)

```yaml
services:
  nginx:        # Reverse proxy, TLS termination, static files
  frontend:     # Next.js (SSR + static)
  backend:      # FastAPI (REST + WebSocket)
  postgres:     # Database
  redis:        # Hot game state, sessions, pub/sub
  # Future:
  # bot-sandbox: # Isolated container for user-uploaded bots
```

Estimated VPS: Hetzner CX32 or similar (~$15/mo, 4 vCPU, 8GB RAM).
Domain + TLS: Cloudflare (free tier) + Let's Encrypt.

Total estimated cost: **$15-25/month** for the core platform.

---

## Cross-Cutting Concerns

| Concern | Approach |
|---|---|
| Logging | Structured JSON logs (structlog for Python) |
| Monitoring | Prometheus metrics + Grafana (lightweight, self-hosted) |
| Error tracking | Sentry (free tier: 5K events/mo) |
| CI/CD | GitHub Actions → build Docker images → SSH deploy |
| DB migrations | Alembic (Python) |
| Type sharing | Generate TypeScript types from Pydantic models (pydantic-to-typescript or similar) |
| Testing | pytest (backend), vitest (frontend), playwright (e2e) |

---

## Subsystem Design Prompts

The following documents should be created by deep-diving into each subsystem.
Each can be designed independently using this document as the shared context.

See: `docs/01-game-engine.md` through `docs/08-carcassonne.md`
