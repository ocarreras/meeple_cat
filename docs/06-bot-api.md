# 06 — Bot / AI Integration API

Two bot modes: external webhooks (user-hosted) and sandboxed uploaded bots
(future). Both implement the same request/response contract. Built-in AI
also uses the same interface internally.

---

## 1. Bot API Contract

### 1.1 Move Request (Platform → Bot)

```
POST {bot_webhook_url}/move
Content-Type: application/json
X-Meeple-Signature: sha256=<hmac_hex>
X-Meeple-Timestamp: 1705312800

{
  "version": "1",
  "game_id": "carcassonne",
  "match_id": "550e8400-e29b-41d4-a716-446655440000",
  "player_id": "bot-abc123",
  "turn_number": 12,
  "phase": "place_tile",
  "action_type": "place_tile",
  "state": {
    // Game-specific PlayerView (same info a human sees)
    // Produced by plugin.state_to_ai_view()
  },
  "valid_actions": [
    { "x": 3, "y": -1, "rotation": 0 },
    { "x": 3, "y": -1, "rotation": 90 },
    { "x": 1, "y": 2, "rotation": 0 }
  ],
  "time_remaining_ms": 30000,
  "metadata": {
    "scores": { "bot-abc123": 25, "player-xyz": 30 },
    "players": [
      { "player_id": "bot-abc123", "display_name": "MyBot", "seat_index": 0 },
      { "player_id": "player-xyz", "display_name": "Alice", "seat_index": 1 }
    ]
  }
}
```

### 1.2 Move Response (Bot → Platform)

```json
{
  "action": {
    "type": "place_tile",
    "payload": { "x": 3, "y": -1, "rotation": 90 }
  },
  "metadata": {
    "confidence": 0.85,
    "thinking_time_ms": 450,
    "model": "mcts-v2",
    "debug": { "nodes_explored": 15000 }
  }
}
```

- `action` (required): Must match one of the `valid_actions` provided.
- `metadata` (optional): Informational only, displayed in replays/debug.

### 1.3 Response Codes

| HTTP Status | Meaning | Platform behavior |
|---|---|---|
| 200 | Success | Parse action, validate, apply |
| 400 | Bot error (malformed) | Log error, apply timeout behavior |
| 408 | Bot timed out | Apply timeout behavior |
| 5xx | Bot server error | Retry once, then apply timeout behavior |

### 1.4 Timeout

The platform waits a maximum of **10 seconds** for a bot response (configurable
per bot, max 30s). If the bot doesn't respond:

1. Log timeout event
2. Apply the game's TimeoutBehavior (typically RANDOM_ACTION for bots)
3. Continue game

### 1.5 Invalid Action Handling

If the bot returns an action not in `valid_actions`:

1. Log the invalid action
2. Retry once with error feedback (send the same request with an added `error` field)
3. If still invalid, apply timeout behavior

Retry request includes:
```json
{
  "...same fields...",
  "error": {
    "type": "invalid_action",
    "message": "Action payload {x: 5, y: 5, rotation: 0} is not in valid_actions",
    "attempt": 2,
    "max_attempts": 2
  }
}
```

---

## 2. Request Authentication (HMAC Signature)

The platform signs every request so bots can verify it's from meeple.cat.

### 2.1 Signing

```python
import hmac
import hashlib
import time

def sign_request(body: bytes, secret: str, timestamp: int) -> str:
    """Generate HMAC-SHA256 signature for request authentication."""
    message = f"{timestamp}.{body.decode()}"
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={signature}"
```

Headers sent:
```
X-Meeple-Signature: sha256=abc123...
X-Meeple-Timestamp: 1705312800
```

### 2.2 Verification (Bot Side)

```python
# Example verification code (provided in bot SDK docs)
def verify_signature(body: bytes, signature: str, timestamp: int, secret: str) -> bool:
    """Verify request is from meeple.cat."""
    # Check timestamp freshness (prevent replay attacks)
    if abs(time.time() - timestamp) > 300:  # 5 min window
        return False

    expected = sign_request(body, secret, timestamp)
    return hmac.compare_digest(signature, expected)
```

The `secret` is generated when the bot is registered and shared with the
bot owner. Shown once on registration, can be rotated.

---

## 3. External Webhook Bots

### 3.1 Registration

```
POST /api/v1/bots
{
  "name": "My Carcassonne Bot",
  "game_id": "carcassonne",
  "bot_type": "webhook",
  "webhook_url": "https://my-server.com/meeple-bot/move",
  "description": "MCTS-based Carcassonne bot"
}

Response:
{
  "id": "bot-abc123",
  "name": "My Carcassonne Bot",
  "game_id": "carcassonne",
  "bot_type": "webhook",
  "webhook_url": "https://my-server.com/meeple-bot/move",
  "signing_secret": "whsec_xxxxxxxxxxxxx",    # SHOWN ONCE
  "is_active": true,
  "created_at": "..."
}
```

### 3.2 Validation on Registration

When a bot is registered, the platform:

1. **URL validation**: Must be HTTPS (except localhost for dev)
2. **Reachability check**: POST a test request to the webhook URL:
   ```json
   {
     "version": "1",
     "type": "validation",
     "challenge": "random-string-123"
   }
   ```
   Bot must respond 200 with: `{ "challenge": "random-string-123" }`
3. **Game validation**: `game_id` must exist in the plugin registry

### 3.3 Health Checking

The platform periodically pings active bots (every 5 minutes):

```
POST {webhook_url}/move
{
  "version": "1",
  "type": "health_check"
}
```

Expected response: 200 with `{ "status": "ok" }`

Bots that fail 3 consecutive health checks are marked inactive.
Owner is notified (if we add notifications later — for V1, just log it).

### 3.4 Rate Limiting

Bots are rate-limited to prevent abuse:
- Max 5 active games simultaneously
- Max 100 move requests per minute per bot
- Webhook URL must be unique per user (can't register the same URL twice)

---

## 4. Sandboxed Uploaded Bots (Future — Interface Design Only)

Design the interface now so the bot adapter layer doesn't need changes later.

### 4.1 Upload Contract

```
POST /api/v1/bots
{
  "name": "My Python Bot",
  "game_id": "carcassonne",
  "bot_type": "uploaded",
  "runtime": "python3.12",
  "description": "Simple heuristic bot"
}
```

Then upload code:
```
POST /api/v1/bots/{bot_id}/upload
Content-Type: multipart/form-data

file: bot.py (or bot.zip)
```

### 4.2 Execution Model

Uploaded bots communicate via stdin/stdout:

```
Platform writes to stdin:
{"version": "1", "game_id": "carcassonne", ..., "valid_actions": [...]}

Bot writes to stdout:
{"action": {"type": "place_tile", "payload": {...}}}
```

This is the simplest sandboxing model — run the bot in a Docker container
with no network access, pipe JSON via stdin/stdout.

### 4.3 Resource Limits (Enforced by Container)

- CPU: 1 vCPU
- Memory: 256 MB
- Time per move: 10 seconds
- Disk: 50 MB (read-only filesystem + 10MB writable /tmp)
- Network: disabled
- No GPU

### 4.4 Supported Runtimes (Future)

| Runtime | Image | Entry point |
|---|---|---|
| Python 3.12 | `python:3.12-slim` | `python bot.py` |
| Node.js 20 | `node:20-slim` | `node bot.js` |
| WASM | Custom | `wasmtime bot.wasm` |

---

## 5. Bot Adapter Layer

The platform uses a uniform adapter interface regardless of bot type:

```python
from abc import ABC, abstractmethod

class BotAdapter(ABC):
    """Uniform interface for calling any type of bot."""

    @abstractmethod
    async def request_move(
        self,
        move_request: MoveRequest,
        timeout_ms: int = 10000,
    ) -> MoveResponse:
        """
        Send game state to bot, get action back.
        Raises BotTimeoutError, BotErrorResponse, BotConnectionError.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if bot is reachable and responsive."""
        ...


class WebhookBotAdapter(BotAdapter):
    """Calls an external webhook bot via HTTP."""

    def __init__(self, webhook_url: str, signing_secret: str):
        self.webhook_url = webhook_url
        self.signing_secret = signing_secret

    async def request_move(self, move_request: MoveRequest, timeout_ms: int = 10000) -> MoveResponse:
        body = move_request.model_dump_json().encode()
        timestamp = int(time.time())
        signature = sign_request(body, self.signing_secret, timestamp)

        async with httpx.AsyncClient(timeout=timeout_ms / 1000) as client:
            response = await client.post(
                self.webhook_url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Meeple-Signature": signature,
                    "X-Meeple-Timestamp": str(timestamp),
                },
            )

        if response.status_code != 200:
            raise BotErrorResponse(response.status_code, response.text)

        return MoveResponse.model_validate_json(response.content)


class BuiltinBotAdapter(BotAdapter):
    """Calls a built-in AI directly (in-process)."""

    def __init__(self, ai_impl: "AIImplementation"):
        self.ai = ai_impl

    async def request_move(self, move_request: MoveRequest, timeout_ms: int = 10000) -> MoveResponse:
        # Run in thread pool to avoid blocking the event loop
        action = await asyncio.wait_for(
            asyncio.to_thread(self.ai.choose_action, move_request),
            timeout=timeout_ms / 1000,
        )
        return MoveResponse(action=action)

    async def health_check(self) -> bool:
        return True  # Always healthy


class SandboxBotAdapter(BotAdapter):
    """Runs uploaded bot code in a sandboxed container. (Future)"""
    # Will use Docker SDK to start container, pipe stdin/stdout
    ...
```

---

## 6. Bot Integration in Game Flow

### 6.1 How Bots Are Triggered

When the engine determines a bot needs to act (via `expected_actions`):

```python
# In GameSession, after broadcasting state update
async def _maybe_trigger_bot(self) -> None:
    """If the next expected action is from a bot, request a move."""
    phase = self.state.current_phase
    for ea in phase.expected_actions:
        player = self._get_player(ea.player_id)
        if player and player.is_bot:
            await self._request_bot_move(player, ea)

async def _request_bot_move(self, player: Player, expected: ExpectedAction) -> None:
    """Ask a bot for its move."""
    adapter = self.bot_manager.get_adapter(player.bot_id)
    plugin = self.plugin

    # Build move request
    ai_view = plugin.state_to_ai_view(
        self.state.game_data,
        self.state.current_phase,
        player.player_id,
        self.state.players,
    )
    valid_actions = plugin.get_valid_actions(
        self.state.game_data,
        self.state.current_phase,
        player.player_id,
    )

    move_request = MoveRequest(
        version="1",
        game_id=self.state.game_id,
        match_id=self.state.match_id,
        player_id=player.player_id,
        turn_number=self.state.turn_number,
        phase=self.state.current_phase.name,
        action_type=expected.action_type,
        state=ai_view,
        valid_actions=valid_actions,
        time_remaining_ms=self.state.player_timers.get(player.player_id, 30000),
        metadata={
            "scores": self.state.scores,
            "players": [p.model_dump() for p in self.state.players],
        },
    )

    try:
        response = await adapter.request_move(move_request)
        action = plugin.parse_ai_action(
            response.action, self.state.current_phase, player.player_id
        )
        # Validate and apply like any other action
        await self.handle_action(action)

    except (BotTimeoutError, BotErrorResponse, BotConnectionError) as e:
        logger.warning(f"Bot {player.bot_id} failed: {e}")
        # Apply timeout behavior (e.g. random action)
        await self._on_timeout(player.player_id)
```

### 6.2 Bot vs Bot Games

Bots can play against each other. The flow is the same — each turn triggers
the next bot. A maximum game duration is enforced (e.g. 1 hour) to prevent
infinite loops.

Bot-vs-bot games can be used for:
- Bot testing
- Tournaments
- Generating training data

---

## 7. Bot Testing

### 7.1 Test Endpoint

```
POST /api/v1/bots/{bot_id}/test
{
  "game_state": "random"    // or a specific state for regression testing
}

Response:
{
  "success": true,
  "response_time_ms": 230,
  "request_sent": { ... },
  "response_received": { ... },
  "action_valid": true,
  "validation_message": null
}
```

The test endpoint:
1. Creates a sample game state using the plugin's `create_initial_state`
2. Advances a few random moves to create a non-trivial state
3. Calls the bot with this state
4. Validates the bot's response
5. Returns the results

### 7.2 Bot Playground (Future)

A web UI where bot developers can:
- See sample game states
- Manually invoke their bot against those states
- View the full request/response cycle
- Run games against built-in AI to test

---

## 8. Bot Rating

Bots participate in the same Glicko-2 rating system as humans. They appear
on leaderboards with a bot badge. Bot ratings are per-game (same as humans).

A bot's rating represents its skill level, which helps matchmaking and lets
users choose appropriately difficult opponents.

---

## 9. Module Structure

```
backend/src/bot/
├── __init__.py
├── models.py            # MoveRequest, MoveResponse, BotConfig
├── adapter.py           # BotAdapter ABC + WebhookBotAdapter + BuiltinBotAdapter
├── manager.py           # BotManager — registry of active bot adapters
├── signing.py           # HMAC signing/verification
├── routes.py            # Bot CRUD REST endpoints
├── health.py            # Periodic health check task
├── testing.py           # Bot test endpoint logic
└── sandbox.py           # SandboxBotAdapter (stub for future)
```
