# Design Prompts — Subsystem Deep Dives

Each prompt below is meant to be used in a fresh conversation with an LLM
to produce a detailed design document for that subsystem. All prompts
reference `docs/00-system-design.md` as shared context.

**How to use**: Copy the prompt, provide `00-system-design.md` as context,
and ask the LLM to produce the corresponding `docs/XX-*.md` file.

---

## Prompt 1: Game Engine Core (`01-game-engine.md`)

```
You are designing the core game engine for meeple.cat, a board game platform.
Read the system design document (00-system-design.md) for full context.

Design the game engine core in detail. This is the most critical subsystem —
every game on the platform plugs into it. The output should be a comprehensive
design doc covering:

1. **Core data models** (Python dataclasses/Pydantic):
   - GameState, Phase, Action, ActionQueue, Event, TransitionResult, PlayerView
   - GameConfig (per-game settings like timer mode, variant rules)
   - ConcurrentMode enum and resolution strategies
   - How state is serialized/deserialized (for Redis and Postgres)

2. **The GamePlugin protocol** — finalize the interface:
   - Validate that it can express: Carcassonne (tile placement + meeple),
     Caylus (multi-phase worker placement), 7 Wonders (simultaneous drafting),
     Agricola (worker placement + harvest), and a trick-taking card game.
   - Walk through each game to verify the protocol handles it. Identify gaps.
   - Define how phases transition: auto-advance vs player-triggered vs timeout.

3. **Action validation pipeline**:
   - How does the engine validate an incoming action?
   - Schema validation → auth check → game rule check → apply
   - Error types and how they're communicated to clients

4. **Event sourcing integration**:
   - Event schema and storage format
   - How to reconstruct state from events
   - Snapshot strategy (if needed for performance)
   - Determinism guarantees — can the same events always reproduce the same state?

5. **Concurrent play resolution**:
   - Detail the commit-reveal flow (submit → lock → reveal → resolve)
   - Detail the time-window flow (window opens → collect → resolve)
   - How does the engine know which mode the current phase uses?

6. **Timer integration points**:
   - How does the engine signal "waiting for player X"?
   - How does timeout trigger the configured TimeoutBehavior?

7. **Game plugin registration & discovery**:
   - How are game plugins registered with the engine?
   - Plugin lifecycle (load, validate, serve)

Be concrete: use Python code examples, not just prose. Think about edge cases:
disconnection mid-action, invalid state recovery, spectator views.
```

---

## Prompt 2: Backend API Design (`02-backend-api.md`)

```
You are designing the backend API for meeple.cat, a board game platform.
Read the system design document (00-system-design.md) for full context.

Design the complete REST + WebSocket API. The output should cover:

1. **REST API endpoints** (OpenAPI-style):
   - Auth: /auth/{provider}/login, /auth/{provider}/callback, /auth/refresh, /auth/me
   - Users: /api/users/{id}, /api/users/{id}/stats
   - Lobby: CRUD for game rooms, join/leave/ready, list available rooms
   - Games: /api/games (catalog), /api/games/{game_id}/leaderboard
   - Matches: /api/matches/{id}, /api/matches/{id}/replay
   - Bots: CRUD for bot registration, bot status

2. **WebSocket protocol** (message types, sequencing):
   - Connection lifecycle (auth, join game, reconnect)
   - Client→Server messages: action, ping, resign, offer_draw, chat
   - Server→Client messages: state_update, action_required, timer_update,
     game_over, error, player_connected, player_disconnected
   - Message format (JSON schema for each message type)
   - Reconnection protocol: how does a client catch up after disconnect?

3. **Error handling**:
   - HTTP error responses (format, error codes)
   - WebSocket error messages
   - Rate limiting strategy

4. **FastAPI application structure**:
   - Router organization
   - Middleware stack (auth, CORS, logging, rate limiting)
   - Dependency injection pattern for game engine, DB, Redis
   - How WebSocket connections are managed (connection manager pattern)

5. **Pagination, filtering, sorting** for list endpoints.

6. **API versioning strategy** (path-based /v1/ or header-based).

Be concrete: provide FastAPI route signatures and Pydantic request/response models.
```

---

## Prompt 3: Frontend Architecture (`03-frontend.md`)

```
You are designing the frontend for meeple.cat, a board game platform.
Read the system design document (00-system-design.md) for full context.

Design the frontend architecture. The output should cover:

1. **Next.js app structure**:
   - Page routes (app router): /, /login, /lobby, /game/{id}, /profile/{id},
     /leaderboard/{game}, /replay/{match_id}
   - Layout hierarchy (shared nav, game-specific layouts)
   - Server components vs client components — where's the boundary?

2. **State management**:
   - What lives in server state (React Query / SWR) vs client state (Zustand)?
   - WebSocket state: how is real-time game state integrated with React?
   - Optimistic updates — do we need them given server-authoritative model?

3. **WebSocket client**:
   - Connection management hook (useWebSocket)
   - Auto-reconnect with exponential backoff
   - Message serialization/deserialization
   - How game state updates flow into React renders

4. **Game rendering architecture** (the hybrid model):
   - Reusable primitives library: Grid, Hand, TokenStack, Dice, ScoreBoard, Timer
   - How game-specific components compose primitives
   - Game component interface: what props does a game renderer receive?
   - Animation strategy for state transitions

5. **Responsive design strategy**:
   - Desktop-first breakpoints
   - How board game UIs adapt to smaller screens
   - Touch interaction considerations for future mobile

6. **Replay viewer**:
   - Event-driven playback controls (play, pause, step, seek)
   - State reconstruction on the client side

7. **Performance considerations**:
   - Bundle splitting per game (don't load Carcassonne code on the lobby page)
   - Canvas vs DOM rendering for game boards

Provide component tree diagrams and TypeScript interface definitions.
```

---

## Prompt 4: Infrastructure & Deployment (`04-infra.md`)

```
You are designing the infrastructure for meeple.cat, a board game platform.
Read the system design document (00-system-design.md) for full context.

Design the complete infrastructure and deployment setup. Target: single VPS,
Docker Compose, under $25/month. The output should cover:

1. **Docker Compose configuration**:
   - All services: nginx, frontend, backend, postgres, redis
   - Network topology (internal network, exposed ports)
   - Volume mounts for persistence (DB data, uploaded bots)
   - Resource limits per container
   - Health checks

2. **Nginx configuration**:
   - TLS termination (Let's Encrypt / certbot)
   - Reverse proxy rules (frontend, backend REST, backend WebSocket)
   - WebSocket upgrade handling
   - Static file serving
   - Rate limiting at proxy level

3. **CI/CD pipeline** (GitHub Actions):
   - Build Docker images on push to main
   - Run tests (backend + frontend)
   - Deploy to VPS (SSH + docker compose pull + restart)
   - Zero-downtime deployment strategy (or acceptable downtime approach)

4. **Backup strategy**:
   - PostgreSQL automated backups (pg_dump, frequency, retention)
   - Where to store backups (object storage? same VPS?)

5. **Monitoring & alerting**:
   - Prometheus + Grafana stack (lightweight)
   - Key metrics: active WebSocket connections, games in progress,
     API latency, error rates, DB connection pool
   - Alerting thresholds

6. **Security**:
   - Firewall rules (ufw / iptables)
   - Container isolation
   - Secret management (environment variables, Docker secrets)
   - DB access control

7. **Scaling plan** (when to move beyond single VPS):
   - What are the bottlenecks? (WebSocket connections, DB, CPU for game logic)
   - At what user count do we need to scale?
   - Migration path to multi-node (add Redis pub/sub, load balancer)

Provide actual configuration files (docker-compose.yml, nginx.conf, GitHub Actions YAML).
```

---

## Prompt 5: Auth System (`05-auth.md`)

```
You are designing the authentication system for meeple.cat, a board game platform.
Read the system design document (00-system-design.md) for full context.

Design the auth system in detail. Providers: Google, GitHub, Discord via OIDC.
The output should cover:

1. **OIDC flow implementation**:
   - Per-provider configuration (endpoints, scopes, user info mapping)
   - CSRF protection (state parameter)
   - Account linking (same email across providers)
   - How to handle provider-specific quirks

2. **JWT implementation**:
   - Access token (short-lived, 15 min) + Refresh token (longer, 7 days)
   - Token payload (claims: user_id, display_name, issued_at)
   - Token refresh flow
   - Token revocation (logout, password change on provider side)

3. **Session management**:
   - Where are refresh tokens stored? (HTTP-only cookie vs Redis)
   - Concurrent session handling (multiple devices)
   - WebSocket authentication (token in query param on connect, validated server-side)

4. **User creation flow**:
   - First login: create user, set defaults from provider profile
   - Subsequent logins: update last_seen, refresh provider data
   - Guest play: is this supported? If so, how?

5. **Authorization**:
   - What resources need authz? (own profile edit, own bots, game actions)
   - Role model (user, admin) — keep it simple
   - How game-level authz works (only players in a game can submit actions)

6. **Python library choice**: authlib vs python-jose vs custom.

Provide FastAPI middleware code examples.
```

---

## Prompt 6: Bot/AI Integration API (`06-bot-api.md`)

```
You are designing the Bot/AI integration layer for meeple.cat, a board game platform.
Read the system design document (00-system-design.md) for full context.

Design the bot system in detail. Two modes: external webhooks and sandboxed uploads.
The output should cover:

1. **Bot API contract** (finalize from system design):
   - Request schema: game state, valid actions, metadata
   - Response schema: chosen action, optional metadata
   - Timeout handling: what if the bot doesn't respond in time?
   - Error handling: malformed response, invalid action, 500 from bot

2. **External webhook bots**:
   - Registration flow (URL, auth, game, validation)
   - Health checking (periodic ping to verify bot is alive)
   - Rate limiting & abuse prevention
   - Authentication: how does the bot verify requests are from meeple.cat?
     (HMAC signature on request body)

3. **Sandboxed uploaded bots** (future, but design the interface now):
   - What languages/runtimes will be supported?
   - Isolation strategy: Docker container per game? WASM? Firecracker?
   - Resource limits (CPU, memory, time per move)
   - How uploaded code accesses the game state (stdin/stdout? HTTP? function call?)
   - Security considerations

4. **Built-in AI adapter**:
   - How built-in AIs implement the same interface
   - Difficulty levels as different bot implementations

5. **Bot tournament/testing**:
   - How can a bot developer test their bot before going live?
   - Can bots play against each other?

6. **Bot lifecycle**:
   - Registration → validation → active → deprecated
   - Bot ratings (same ELO system as humans?)

Provide the full OpenAPI spec for the bot-facing API.
```

---

## Prompt 7: Replay & Ranking Systems (`07-replay-rankings.md`)

```
You are designing the replay and ranking systems for meeple.cat.
Read the system design document (00-system-design.md) for full context.

Design both systems in detail:

**Replay System:**
1. Event storage schema and indexing strategy
2. Replay API: how clients fetch and paginate event logs
3. Client-side replay engine: how to reconstruct state from events
4. Sharing replays: public URLs, embedding
5. Annotated replays: can users/AI add commentary to specific moves?
6. Storage cost estimation (events per game, average game length)

**Ranking System:**
7. Algorithm choice: ELO vs Glicko-2 vs TrueSkill — pros/cons for this use case
8. Rating calculation: when and how ratings update
9. Per-game leaderboards: query patterns, caching strategy
10. Seasonal rankings: resets, historical tracking
11. Rating display: how to show uncertainty (Glicko-2 deviation)
12. Anti-abuse: how to prevent rating manipulation (smurfing, sandbagging, win trading)
13. Provisional ratings for new players

Provide SQL queries for common leaderboard operations and the rating update algorithm.
```

---

## Prompt 8: Carcassonne Implementation (`08-carcassonne.md`)

```
You are implementing Carcassonne as the first game on meeple.cat.
Read the system design document (00-system-design.md) for full context,
especially the game engine design (01-game-engine.md).

Design the complete Carcassonne implementation. The output should cover:

1. **Game state model**:
   - Board representation (tile grid, placed tiles with rotation)
   - Tile definitions (all 72 base game tiles, edge types: city/road/field/monastery)
   - Meeple tracking (placed on features, available per player)
   - Feature tracking (roads, cities, fields, monasteries — which tiles they span)
   - Tile bag (remaining tiles, draw order — deterministic from seed for replays)

2. **Phases and actions**:
   - Phase: draw_tile (automatic, system draws for current player)
   - Phase: place_tile (player chooses position + rotation)
   - Phase: place_meeple (optional, player chooses feature on placed tile)
   - Phase: score_completed (automatic, check for completed features)
   - End-game scoring (farmers, incomplete features)

3. **Validation rules**:
   - Tile placement: edges must match adjacent tiles
   - Meeple placement: feature must not already be claimed
   - Legal move generation (all valid positions + rotations for current tile)

4. **Scoring logic**:
   - Completed city, road, monastery scoring
   - Field scoring (end-game only, the trickiest part)
   - How features merge (two cities joining, shared roads)

5. **PlayerView filtering**:
   - Hidden info: remaining tile bag composition (maybe show count only?)
   - Visible: board, placed meeples, scores, current tile to place

6. **Frontend components** (Carcassonne-specific):
   - Board renderer (tile grid, zoom, pan)
   - Tile preview (current tile to place with rotation controls)
   - Meeple placement UI (click on feature)
   - Score display

7. **AI state serialization**:
   - How to represent the board state for a bot
   - How to encode valid placements

Walk through a complete 3-player game (5-6 turns) to validate the model works
end to end. Identify edge cases.
```

---

## Implementation Order

Recommended sequence for building the platform:

1. **Game Engine Core** (01) — Foundation everything else depends on
2. **Carcassonne game logic** (08) — Validate the engine works with a real game
3. **Backend API** (02) — REST + WebSocket server
4. **Auth** (05) — User identity
5. **Frontend** (03) — Playable UI
6. **Infrastructure** (04) — Deploy it
7. **Bot API** (06) — AI integration
8. **Replay & Rankings** (07) — Polish features
