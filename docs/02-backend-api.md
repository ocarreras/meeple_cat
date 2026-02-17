# 02 — Backend API Design

The backend exposes a REST API for resource CRUD and a WebSocket API for
real-time game play. Both run on the same FastAPI application.

---

## 1. API Versioning

Path-based: all endpoints under `/api/v1/`. This is simple, explicit, and
easy to manage with FastAPI routers.

```python
from fastapi import FastAPI, APIRouter

app = FastAPI(title="meeple.cat", version="0.1.0")
v1 = APIRouter(prefix="/api/v1")
# Mount sub-routers onto v1
app.include_router(v1)
```

---

## 2. REST API Endpoints

### 2.1 Auth

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/auth/{provider}/login` | Redirect to OIDC provider | No |
| GET | `/auth/{provider}/callback` | OIDC callback, issues JWT | No |
| POST | `/auth/refresh` | Refresh access token | Refresh token |
| POST | `/auth/logout` | Revoke refresh token | Yes |
| GET | `/api/v1/auth/me` | Current user info | Yes |

### 2.2 Users

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/api/v1/users/{user_id}` | Get user profile | No |
| PATCH | `/api/v1/users/me` | Update own profile | Yes |
| GET | `/api/v1/users/{user_id}/stats` | User game stats | No |
| GET | `/api/v1/users/{user_id}/matches` | User match history | No |

```python
# Response models
class UserPublic(BaseModel):
    id: str
    display_name: str
    avatar_url: str | None
    bio: str | None
    country: str | None
    created_at: datetime

class UserStats(BaseModel):
    user_id: str
    games: dict[str, GameStats]   # Per game_id

class GameStats(BaseModel):
    game_id: str
    rating: float
    games_played: int
    wins: int
    losses: int
    draws: int
    win_rate: float
```

### 2.3 Games Catalog

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/api/v1/games` | List available games | No |
| GET | `/api/v1/games/{game_id}` | Game details + config schema | No |
| GET | `/api/v1/games/{game_id}/leaderboard` | Top players | No |

```python
class GameInfo(BaseModel):
    game_id: str
    display_name: str
    min_players: int
    max_players: int
    description: str
    config_schema: dict         # JSON Schema for game options

class LeaderboardEntry(BaseModel):
    rank: int
    user: UserPublic
    rating: float
    games_played: int
    win_rate: float

class LeaderboardResponse(BaseModel):
    game_id: str
    entries: list[LeaderboardEntry]
    total: int
    page: int
    page_size: int
```

### 2.4 Lobby / Game Rooms

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/api/v1/rooms` | List open rooms | No |
| POST | `/api/v1/rooms` | Create a room | Yes |
| GET | `/api/v1/rooms/{room_id}` | Room details | No |
| POST | `/api/v1/rooms/{room_id}/join` | Join a room | Yes |
| POST | `/api/v1/rooms/{room_id}/leave` | Leave a room | Yes |
| POST | `/api/v1/rooms/{room_id}/ready` | Toggle ready status | Yes |
| POST | `/api/v1/rooms/{room_id}/start` | Start the game (creator only) | Yes |
| POST | `/api/v1/rooms/{room_id}/add-bot` | Add a bot to a seat | Yes |

```python
class CreateRoomRequest(BaseModel):
    game_id: str
    max_players: int
    config: dict = {}            # Game-specific options
    timer: TimerConfig = TimerConfig()
    is_private: bool = False     # Private rooms need an invite code

class RoomResponse(BaseModel):
    id: str
    game_id: str
    created_by: UserPublic
    config: dict
    timer: TimerConfig
    status: str                  # "waiting", "starting", "in_game"
    max_players: int
    seats: list[SeatInfo]
    invite_code: str | None      # For private rooms
    created_at: datetime

class SeatInfo(BaseModel):
    seat_index: int
    user: UserPublic | None
    bot: BotInfo | None
    is_ready: bool
    is_empty: bool

# Quick play shortcut
# POST /api/v1/rooms/quick-play
class QuickPlayRequest(BaseModel):
    game_id: str
    opponent: str = "ai"         # "ai" or "matchmaking"
    config: dict = {}
    timer: TimerConfig = TimerConfig()
```

### 2.5 Matches

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/api/v1/matches/{match_id}` | Match info (metadata, players, result) | No |
| GET | `/api/v1/matches/{match_id}/replay` | Full event log for replay | No |
| GET | `/api/v1/matches/{match_id}/events` | Paginated event stream | No |

```python
class MatchResponse(BaseModel):
    id: str
    game_id: str
    status: str
    config: dict
    players: list[MatchPlayerInfo]
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    result: GameResult | None

class MatchPlayerInfo(BaseModel):
    player_id: str
    display_name: str
    seat_index: int
    is_bot: bool
    score: float | None
    result: str | None           # "win", "loss", "draw"

class ReplayResponse(BaseModel):
    match: MatchResponse
    initial_state: dict          # Public view of starting state
    events: list[ReplayEvent]

class ReplayEvent(BaseModel):
    sequence_number: int
    event_type: str
    player_id: str | None
    payload: dict
    timestamp: datetime
```

### 2.6 Bots

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/api/v1/bots` | List user's bots | Yes |
| POST | `/api/v1/bots` | Register a bot | Yes |
| GET | `/api/v1/bots/{bot_id}` | Bot details | No |
| PATCH | `/api/v1/bots/{bot_id}` | Update bot config | Yes (owner) |
| DELETE | `/api/v1/bots/{bot_id}` | Deactivate bot | Yes (owner) |
| POST | `/api/v1/bots/{bot_id}/test` | Test bot with a sample game state | Yes (owner) |

```python
class CreateBotRequest(BaseModel):
    name: str
    game_id: str
    bot_type: str                # "webhook" or "uploaded"
    webhook_url: str | None      # Required for webhook type
    auth_header: str | None      # Optional auth for webhook
    description: str = ""

class BotResponse(BaseModel):
    id: str
    name: str
    game_id: str
    owner: UserPublic
    bot_type: str
    is_active: bool
    rating: float | None
    games_played: int
    created_at: datetime

class BotTestResponse(BaseModel):
    success: bool
    response_time_ms: int
    action_returned: dict | None
    error: str | None
```

---

## 3. WebSocket Protocol

### 3.1 Connection

```
Endpoint: /ws/game/{match_id}

Query parameters:
  token: string     # JWT access token
  spectator: bool   # Optional, default false

Connection flow:
  1. Client connects to ws://host/ws/game/{match_id}?token=xxx
  2. Server validates JWT
  3. Server validates player is in this match (or spectator flag)
  4. Server sends "connected" message with current PlayerView
  5. Bidirectional message exchange
  6. Either side can close the connection
```

### 3.2 Message Format

All messages are JSON with a `type` field:

```typescript
interface WSMessage {
  type: string;
  payload?: any;
  timestamp?: string;    // ISO 8601, set by server
  seq?: number;          // Server-side sequence number for ordering
}
```

### 3.3 Client → Server Messages

#### `action` — Submit a game action
```json
{
  "type": "action",
  "payload": {
    "action_type": "place_tile",
    "data": { "x": 3, "y": -1, "rotation": 90 }
  }
}
```

#### `ping` — Keep-alive
```json
{ "type": "ping" }
```

#### `resign` — Forfeit the game
```json
{ "type": "resign" }
```

#### `offer_draw` — Propose a draw
```json
{ "type": "offer_draw" }
```

#### `accept_draw` — Accept draw offer
```json
{ "type": "accept_draw" }
```

#### `chat` — In-game chat message
```json
{
  "type": "chat",
  "payload": { "message": "Good game!" }
}
```

### 3.4 Server → Client Messages

#### `connected` — Initial state on connect
```json
{
  "type": "connected",
  "payload": {
    "match_id": "uuid",
    "player_id": "your-uuid",
    "view": { /* PlayerView */ },
    "server_time": "2025-01-15T10:00:00Z"
  },
  "seq": 0
}
```

#### `state_update` — Game state changed
```json
{
  "type": "state_update",
  "payload": {
    "view": { /* PlayerView */ },
    "events": [
      { "event_type": "tile_placed", "player_id": "p1", "payload": {...} }
    ],
    "caused_by": "action"
  },
  "seq": 42
}
```

#### `action_required` — It's your turn
```json
{
  "type": "action_required",
  "payload": {
    "phase": "place_tile",
    "expected_action": "place_tile",
    "valid_actions": [ ... ],
    "timeout_ms": 30000
  },
  "seq": 43
}
```

#### `action_committed` — Your concurrent action was received
```json
{
  "type": "action_committed",
  "payload": { "phase": "choose_card" },
  "seq": 44
}
```

#### `players_committed` — Who has committed (concurrent phases)
```json
{
  "type": "players_committed",
  "payload": {
    "committed": ["player-1", "player-3"],
    "waiting_for": ["player-2"]
  },
  "seq": 45
}
```

#### `timer_update` — Timer tick (sent every 1s while a timer is active)
```json
{
  "type": "timer_update",
  "payload": {
    "player_timers": {
      "player-1": 25000,
      "player-2": 30000
    },
    "active_player": "player-1"
  },
  "seq": 46
}
```

#### `game_over` — Game ended
```json
{
  "type": "game_over",
  "payload": {
    "result": {
      "winners": ["player-2"],
      "final_scores": { "player-1": 85, "player-2": 102, "player-3": 77 },
      "reason": "normal"
    }
  },
  "seq": 100
}
```

#### `error` — Something went wrong
```json
{
  "type": "error",
  "payload": {
    "code": "invalid_action",
    "message": "Tile edges don't match adjacent tiles"
  },
  "seq": 47
}
```

#### `player_connected` / `player_disconnected`
```json
{
  "type": "player_disconnected",
  "payload": {
    "player_id": "player-3",
    "grace_period_ms": 60000
  },
  "seq": 48
}
```

#### `draw_offered` / `draw_accepted` / `draw_declined`
```json
{
  "type": "draw_offered",
  "payload": { "offered_by": "player-1" },
  "seq": 49
}
```

#### `chat_message`
```json
{
  "type": "chat_message",
  "payload": {
    "player_id": "player-1",
    "display_name": "Alice",
    "message": "Good game!"
  },
  "seq": 50
}
```

### 3.5 Reconnection Protocol

```
1. Client detects WebSocket close (network drop, page refresh, etc.)
2. Client reconnects to same /ws/game/{match_id}?token=xxx
3. Client includes header: X-Last-Seq: 42 (last seq it received)
4. Server:
   a. Validates token + player membership
   b. Sends "connected" with current PlayerView
   c. Sends any events the client missed (seq > 42)
   d. Resumes normal message flow
5. Timer resumes for this player (was paused during disconnect)
```

The server keeps a recent message buffer per match (last N messages or last
T seconds) in Redis for fast reconnection. For longer disconnects, the client
receives the current state and can request replay events via REST if needed.

### 3.6 Sequence Numbers

Every server→client message has a monotonically increasing `seq` number per
match. This enables:
- Gap detection (client knows it missed messages)
- Deduplication (on reconnect, server can replay from a seq)
- Ordering guarantee (client can reorder if messages arrive out of order)

---

## 4. FastAPI Application Structure

### 4.1 Router Organization

```
backend/src/
├── main.py                  # App factory, startup/shutdown, middleware
├── api/
│   ├── __init__.py
│   ├── deps.py              # Dependency injection (DB, Redis, auth, plugin registry)
│   ├── auth_routes.py       # /auth/* routes
│   ├── user_routes.py       # /api/v1/users/*
│   ├── game_routes.py       # /api/v1/games/*
│   ├── room_routes.py       # /api/v1/rooms/*
│   ├── match_routes.py      # /api/v1/matches/*
│   └── bot_routes.py        # /api/v1/bots/*
├── ws/
│   ├── __init__.py
│   ├── handler.py           # WebSocket endpoint + message routing
│   └── connection_manager.py # Track active connections per match
└── middleware/
    ├── auth.py              # JWT validation middleware
    ├── cors.py              # CORS config
    ├── rate_limit.py        # Rate limiting
    └── logging.py           # Request/response logging
```

### 4.2 Dependency Injection

```python
from fastapi import Depends
from functools import lru_cache

# Database session
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session

# Redis client
async def get_redis() -> Redis:
    return redis_pool

# Current authenticated user
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_jwt(token)
    user = await db.get(User, payload["sub"])
    if not user:
        raise HTTPException(401, "User not found")
    return user

# Optional auth (for endpoints that work with or without auth)
async def get_optional_user(
    token: str | None = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if not token:
        return None
    try:
        return await get_current_user(token, db)
    except HTTPException:
        return None

# Plugin registry
def get_plugin_registry() -> PluginRegistry:
    return app.state.plugin_registry

# Game session manager
def get_session_manager() -> GameSessionManager:
    return app.state.session_manager
```

### 4.3 WebSocket Connection Manager

```python
class ConnectionManager:
    """
    Manages WebSocket connections for all active matches.
    Maps match_id → player_id → WebSocket connection.
    """

    def __init__(self):
        self._connections: dict[str, dict[str, WebSocket]] = {}
        self._spectators: dict[str, list[WebSocket]] = {}
        self._message_buffer: dict[str, list[dict]] = {}  # Recent messages per match

    async def connect(
        self, match_id: str, player_id: str, websocket: WebSocket
    ) -> None:
        await websocket.accept()
        if match_id not in self._connections:
            self._connections[match_id] = {}
        self._connections[match_id][player_id] = websocket

    async def connect_spectator(
        self, match_id: str, websocket: WebSocket
    ) -> None:
        await websocket.accept()
        if match_id not in self._spectators:
            self._spectators[match_id] = []
        self._spectators[match_id].append(websocket)

    async def disconnect(self, match_id: str, player_id: str) -> None:
        if match_id in self._connections:
            self._connections[match_id].pop(player_id, None)

    async def send_to_player(
        self, match_id: str, player_id: str, message: dict
    ) -> None:
        ws = self._connections.get(match_id, {}).get(player_id)
        if ws:
            await ws.send_json(message)

    async def broadcast_to_match(self, match_id: str, message: dict) -> None:
        """Send to all players + spectators in a match."""
        for ws in self._connections.get(match_id, {}).values():
            await ws.send_json(message)
        for ws in self._spectators.get(match_id, []):
            await ws.send_json(message)

    async def send_to_each_player(
        self, match_id: str, messages: dict[str, dict]
    ) -> None:
        """Send different messages to different players (filtered views)."""
        for player_id, message in messages.items():
            await self.send_to_player(match_id, player_id, message)

    def get_missed_messages(
        self, match_id: str, after_seq: int
    ) -> list[dict]:
        """Get messages a reconnecting client missed."""
        buffer = self._message_buffer.get(match_id, [])
        return [m for m in buffer if m.get("seq", 0) > after_seq]

    async def cleanup_match(self, match_id: str) -> None:
        """Remove all connections for a finished match."""
        self._connections.pop(match_id, None)
        self._spectators.pop(match_id, None)
        self._message_buffer.pop(match_id, None)
```

### 4.4 WebSocket Endpoint

```python
@app.websocket("/ws/game/{match_id}")
async def websocket_game(
    websocket: WebSocket,
    match_id: str,
    token: str = Query(...),
    spectator: bool = Query(False),
    last_seq: int = Query(0, alias="last_seq"),
):
    # Authenticate
    try:
        user = await authenticate_ws(token)
    except AuthError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Get game session
    session = session_manager.get_session(match_id)
    if not session:
        await websocket.close(code=4004, reason="Game not found")
        return

    # Connect
    if spectator:
        await conn_manager.connect_spectator(match_id, websocket)
    else:
        if not session.has_player(user.id):
            await websocket.close(code=4003, reason="Not a player in this game")
            return
        await conn_manager.connect(match_id, user.id, websocket)
        await session.on_player_connected(user.id)

    # Send current state + missed messages
    view = session.get_view_for(user.id if not spectator else None)
    await websocket.send_json({
        "type": "connected",
        "payload": {"match_id": match_id, "player_id": user.id, "view": view.dict()},
        "seq": session.current_seq,
    })
    missed = conn_manager.get_missed_messages(match_id, last_seq)
    for msg in missed:
        await websocket.send_json(msg)

    # Message loop
    try:
        while True:
            data = await websocket.receive_json()
            await _handle_ws_message(session, user.id, data, spectator)
    except WebSocketDisconnect:
        if not spectator:
            await conn_manager.disconnect(match_id, user.id)
            await session.on_player_disconnected(user.id)

async def _handle_ws_message(
    session: GameSession, player_id: str, data: dict, is_spectator: bool
):
    msg_type = data.get("type")

    if msg_type == "ping":
        return  # No-op, connection is alive

    if is_spectator:
        return  # Spectators can only receive

    if msg_type == "action":
        action = Action(
            action_type=data["payload"]["action_type"],
            player_id=PlayerId(player_id),
            payload=data["payload"].get("data", {}),
            timestamp=datetime.utcnow(),
        )
        await session.handle_action(action)

    elif msg_type == "resign":
        await session.handle_resignation(player_id)

    elif msg_type == "offer_draw":
        await session.handle_draw_offer(player_id)

    elif msg_type == "accept_draw":
        await session.handle_draw_accept(player_id)

    elif msg_type == "chat":
        message = data.get("payload", {}).get("message", "")
        if message:
            await session.handle_chat(player_id, message)
```

### 4.5 Middleware Stack

```python
def create_app() -> FastAPI:
    app = FastAPI(title="meeple.cat", version="0.1.0")

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting (using slowapi or custom)
    app.add_middleware(RateLimitMiddleware, default_limit="60/minute")

    # Request logging
    app.add_middleware(LoggingMiddleware)

    # Routers
    app.include_router(auth_router)
    app.include_router(v1_router, prefix="/api/v1")

    # Startup
    @app.on_event("startup")
    async def startup():
        app.state.db = await init_db()
        app.state.redis = await init_redis()
        app.state.plugin_registry = PluginRegistry()
        app.state.plugin_registry.connect_grpc(settings.game_engine_grpc_url)
        app.state.session_manager = GameSessionManager(...)
        app.state.connection_manager = ConnectionManager()
        # Recover active games from Redis
        await app.state.session_manager.recover_active_games()

    @app.on_event("shutdown")
    async def shutdown():
        await app.state.redis.close()
        await app.state.db.dispose()

    return app
```

---

## 5. Error Handling

### 5.1 HTTP Error Responses

```python
class ErrorResponse(BaseModel):
    error: str           # Machine-readable code
    message: str         # Human-readable message
    details: dict = {}   # Additional context

# Example: 422 Unprocessable Entity
{
    "error": "validation_error",
    "message": "Invalid game configuration",
    "details": {
        "fields": {
            "max_players": "Must be between 2 and 5 for Carcassonne"
        }
    }
}
```

Standard error codes:

| HTTP | Code | When |
|---|---|---|
| 400 | `bad_request` | Malformed request |
| 401 | `unauthorized` | Missing or invalid token |
| 403 | `forbidden` | Authenticated but not allowed |
| 404 | `not_found` | Resource doesn't exist |
| 409 | `conflict` | State conflict (room full, already joined) |
| 422 | `validation_error` | Request validation failed |
| 429 | `rate_limited` | Too many requests |
| 500 | `internal_error` | Unexpected server error |

### 5.2 Rate Limiting

| Endpoint group | Limit |
|---|---|
| Auth | 10/min |
| Room CRUD | 30/min |
| WebSocket actions | 120/min (2/sec) |
| Bot test | 5/min |
| General API | 60/min |

---

## 6. Pagination

List endpoints use cursor-based pagination for consistency:

```python
class PaginationParams(BaseModel):
    cursor: str | None = None    # Opaque cursor for next page
    limit: int = 20              # Items per page (max 100)

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None      # None if last page
    total: int | None            # Total count (optional, expensive)
```

For leaderboards, offset-based is acceptable (users want to see "page 3"):

```python
class LeaderboardParams(BaseModel):
    page: int = 1
    page_size: int = 25          # Max 100
```

---

## 7. Lobby WebSocket (Optional Enhancement)

For real-time lobby updates (new rooms, player joins, rooms starting),
a separate lightweight WebSocket:

```
Endpoint: /ws/lobby

Server → Client messages:
  room_created, room_updated, room_closed, room_started

No auth required (public lobby view).
```

This is optional for V1 — polling the rooms list every few seconds works fine
initially.
