# 01 — Game Engine Core

The game engine is the abstract framework that every game on meeple.cat plugs
into. It must be generic enough to model turn-based, phase-based, and
simultaneous-play board games while remaining simple enough that implementing
a new game feels natural, not bureaucratic.

**Design principle**: The engine owns the *flow* (whose turn, what phase,
timeouts, event recording, view filtering). The game plugin owns the *rules*
(what's legal, what happens when you do X, who wins).

> **Architecture note (Feb 2025):** Game logic now runs in a dedicated Rust
> engine (`game-engine/`) that communicates with the Python backend via gRPC.
> The `GamePlugin` protocol defined below remains the contract — the Python
> `GrpcGamePlugin` adapter (`backend/src/engine/grpc_plugin.py`) implements
> it by translating each method call into a gRPC request to the Rust engine.
> The data models, session orchestration, event sourcing, and view
> broadcasting all remain in Python. See `docs/09-rust-mcts-engine.md` for
> the Rust engine architecture.

---

## 1. Core Data Models

All models use Pydantic v2 for validation and serialization. Game-specific
state is stored as typed dictionaries / nested models — the engine doesn't
inspect it, but games must declare its shape.

### 1.1 Identifiers

```python
from typing import NewType

PlayerId = NewType("PlayerId", str)   # UUID string
MatchId  = NewType("MatchId", str)    # UUID string
GameId   = NewType("GameId", str)     # slug e.g. "carcassonne"
```

### 1.2 Player

```python
from pydantic import BaseModel

class Player(BaseModel):
    """A participant in a match (human or bot)."""
    player_id: PlayerId
    display_name: str
    seat_index: int           # 0-based, determines turn order
    is_bot: bool = False
    bot_id: str | None = None
```

### 1.3 GameConfig

```python
class TimerMode(str, Enum):
    FISCHER  = "fischer"
    BYOYOMI  = "byoyomi"
    SIMPLE   = "simple"
    TOTAL    = "total"
    NONE     = "none"         # No timer (casual / AI-only)

class TimeoutBehavior(str, Enum):
    LOSE_GAME     = "lose_game"
    LOSE_TURN     = "lose_turn"
    RANDOM_ACTION = "random_action"
    FORCE_PASS    = "force_pass"

class TimerConfig(BaseModel):
    mode: TimerMode = TimerMode.NONE
    base_time_ms: int = 0
    increment_ms: int = 0
    periods: int = 1                    # For byo-yomi
    period_time_ms: int = 0             # For byo-yomi
    timeout_behavior: TimeoutBehavior = TimeoutBehavior.LOSE_TURN

class GameConfig(BaseModel):
    """
    Configuration for a match. Contains timer settings and game-specific
    options. The `options` dict is validated by the game plugin — the engine
    passes it through without inspecting it.
    """
    timer: TimerConfig = TimerConfig()
    options: dict = {}                  # Game-specific (e.g. expansions, variants)
    random_seed: int | None = None      # For deterministic replay. If None, generated.
```

### 1.4 Phase & Action Queue

The phase system is the heart of the turn model. A phase represents a
discrete stage in the game flow where one or more players must act.

```python
class ConcurrentMode(str, Enum):
    SEQUENTIAL    = "sequential"     # One player acts at a time
    COMMIT_REVEAL = "commit_reveal"  # All submit hidden, then reveal
    TIME_WINDOW   = "time_window"    # All submit within a window

class ExpectedAction(BaseModel):
    """Describes what the engine is waiting for."""
    player_id: PlayerId | None       # None = ALL players must act
    action_type: str                 # e.g. "place_tile", "choose_card"
    constraints: dict = {}           # Game-specific hints for UI / validation
    timeout_ms: int | None = None    # Override per-action timeout (None = use game timer)

class Phase(BaseModel):
    """
    A named stage in the game flow.

    Phases are NOT predefined in a fixed sequence — the game plugin decides
    dynamically what phase comes next via TransitionResult. This allows for
    conditional branching (e.g. "if player built a castle, enter bonus_action
    phase; otherwise skip to next player").
    """
    name: str                                      # e.g. "place_tile"
    concurrent_mode: ConcurrentMode = ConcurrentMode.SEQUENTIAL
    expected_actions: list[ExpectedAction] = []     # What we're waiting for
    auto_resolve: bool = False                      # If True, engine resolves immediately (no player input)
    metadata: dict = {}                             # Game-specific phase data
```

**Key insight**: Phases are not a static list. The game plugin returns the
*next* phase as part of `TransitionResult`. This makes the flow a dynamic
state machine, not a fixed cycle. Complex games like Caylus need this —
the phase after "activate buildings" depends on *which* buildings were activated.

### 1.5 Action

```python
class Action(BaseModel):
    """
    A player's input. The engine validates the envelope (player_id, action_type,
    match context). The game plugin validates the payload (is this move legal?).
    """
    action_type: str                # Must match an ExpectedAction.action_type
    player_id: PlayerId
    payload: dict                   # Game-specific data (e.g. {x: 3, y: -1, rotation: 90})
    timestamp: datetime | None = None  # Set by server on receipt
```

### 1.6 Event

```python
class Event(BaseModel):
    """
    Immutable record of something that happened. Actions are *intent*;
    events are *facts*. One action may produce multiple events.

    Example: action "place_tile" may produce events:
      - tile_placed {x, y, rotation, tile_id}
      - feature_completed {feature_type: "city", tiles: [...], scorer: "player-1"}
      - score_updated {player_id: "player-1", delta: 10, new_total: 35}
    """
    event_type: str
    player_id: PlayerId | None = None   # None for system/automatic events
    payload: dict = {}
    # sequence_number and timestamp are added by the engine when persisting,
    # not by the game plugin when creating the event.
```

### 1.7 GameState

```python
class GameState(BaseModel):
    """
    Complete game state. The engine owns the envelope fields; the game plugin
    owns `game_data`.

    This is the single source of truth — everything can be reconstructed from
    initial_state + events, and this is the materialized result of that.
    """
    # --- Engine-managed fields ---
    match_id: MatchId
    game_id: GameId
    players: list[Player]
    current_phase: Phase
    status: GameStatus                 # WAITING, ACTIVE, PAUSED, FINISHED, ABANDONED
    turn_number: int = 0               # Incremented by engine after each full round
    action_number: int = 0             # Monotonic counter for all actions in the match
    config: GameConfig

    # --- Timer state (engine-managed) ---
    player_timers: dict[PlayerId, int] = {}  # Remaining time in ms per player

    # --- Game-managed fields ---
    game_data: dict                    # Opaque to the engine. Game plugin reads/writes this.
    scores: dict[PlayerId, float] = {} # Maintained by game plugin, read by engine for display

    # --- Concurrent action buffer (engine-managed) ---
    committed_actions: dict[PlayerId, Action] = {}  # For COMMIT_REVEAL phases

class GameStatus(str, Enum):
    WAITING   = "waiting"     # Room created, waiting for players
    ACTIVE    = "active"      # Game in progress
    PAUSED    = "paused"      # Temporarily paused (disconnection grace period)
    FINISHED  = "finished"    # Game ended normally
    ABANDONED = "abandoned"   # Game ended due to player leaving / timeout
```

### 1.8 TransitionResult

```python
class TransitionResult(BaseModel):
    """
    The result of applying an action or resolving a phase. This is what the
    game plugin returns to the engine.
    """
    game_data: dict                      # Updated game-specific state
    events: list[Event]                  # What happened (for event log)
    next_phase: Phase                    # What phase comes next
    scores: dict[PlayerId, float] = {}   # Updated scores
    game_over: GameResult | None = None  # Non-None if game has ended

class GameResult(BaseModel):
    """Final result of a completed game."""
    winners: list[PlayerId]              # Can be multiple (tie)
    final_scores: dict[PlayerId, float]
    reason: str = "normal"               # "normal", "timeout", "resignation", "abandonment"
    details: dict = {}                   # Game-specific end-of-game data
```

### 1.9 PlayerView

```python
class PlayerView(BaseModel):
    """
    What a specific player (or spectator) can see. Generated by the game
    plugin's get_player_view(). The engine wraps this with common fields.
    """
    # --- Engine-provided (same for all viewers) ---
    match_id: MatchId
    game_id: GameId
    players: list[Player]
    current_phase: Phase
    status: GameStatus
    turn_number: int
    scores: dict[PlayerId, float]
    player_timers: dict[PlayerId, int]

    # --- Game-provided (filtered per viewer) ---
    game_data: dict                      # Filtered game state
    valid_actions: list[dict] = []       # Legal actions for THIS player (empty if not their turn)

    # --- Viewer context ---
    viewer_id: PlayerId | None = None    # None for spectators
    is_spectator: bool = False
```

---

## 2. The GamePlugin Protocol

### 2.1 Full Protocol Definition

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class GamePlugin(Protocol):
    """
    Interface that every game must implement. The engine calls these methods;
    the game never calls the engine directly.

    IMPORTANT: All methods must be PURE FUNCTIONS with respect to their inputs.
    They must not have side effects, access external state, or use randomness
    outside of what's encoded in game_data (which includes the seeded RNG state).
    This is critical for deterministic replay.
    """

    # --- Metadata (class-level constants) ---
    game_id: ClassVar[GameId]
    display_name: ClassVar[str]
    min_players: ClassVar[int]
    max_players: ClassVar[int]
    description: ClassVar[str]
    config_schema: ClassVar[dict]        # JSON Schema for GameConfig.options

    # --- Setup ---

    def create_initial_state(
        self,
        players: list[Player],
        config: GameConfig,
    ) -> tuple[dict, Phase, list[Event]]:
        """
        Create the initial game_data, first phase, and setup events.

        The random_seed in config must be used for all randomness (shuffle, etc.)
        so that the game is replayable from seed + actions.

        Returns:
            game_data: The initial game-specific state
            first_phase: The opening phase
            setup_events: Events describing the setup (e.g. "deck_shuffled", "tiles_dealt")
        """
        ...

    def validate_config(self, options: dict) -> list[str]:
        """
        Validate game-specific config options. Return list of error messages
        (empty = valid). Called when a room is created.
        """
        ...

    # --- Core game loop ---

    def get_valid_actions(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
    ) -> list[dict]:
        """
        Return all legal actions for this player in the current phase.

        Returns a list of action payloads (dicts). Each dict can be directly
        used as Action.payload with the phase's expected action_type.

        For phases where the player has no actions (not their turn, or the
        phase doesn't involve them), return [].

        For games with huge action spaces (e.g. Go), this may return a
        description of the action space rather than enumeration:
          [{"type": "place_stone", "valid_positions": [[0,0], [0,1], ...]}]
        """
        ...

    def validate_action(
        self,
        game_data: dict,
        phase: Phase,
        action: Action,
    ) -> str | None:
        """
        Check if an action is legal. Return None if valid, error message if not.

        This is separate from get_valid_actions because:
        1. validate is called on every incoming action (must be fast)
        2. get_valid_actions may be expensive and is only called on demand
        """
        ...

    def apply_action(
        self,
        game_data: dict,
        phase: Phase,
        action: Action,
        players: list[Player],
    ) -> TransitionResult:
        """
        Apply a validated action to the game state.

        PRECONDITION: validate_action() has already returned None for this action.

        The returned TransitionResult contains:
        - game_data: the new game-specific state
        - events: what happened
        - next_phase: what phase to enter next
        - scores: updated scores
        - game_over: non-None if the game has ended

        For sequential phases, this is called once per action.
        For concurrent phases, use resolve_concurrent_actions instead.
        """
        ...

    # --- View filtering ---

    def get_player_view(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId | None,  # None = spectator
        players: list[Player],
    ) -> dict:
        """
        Filter game_data to only what this player can see.

        Examples of filtering:
        - Carcassonne: hide remaining tile bag contents, show only count
        - Poker: hide other players' hole cards
        - Caylus: everything visible (open information game)

        For spectators (player_id=None), show the "broadcast" view —
        typically the same as a player view but with no hidden info revealed.
        Some games may choose to show everything to spectators with a delay.
        """
        ...

    # --- Concurrent play ---

    def resolve_concurrent_actions(
        self,
        game_data: dict,
        phase: Phase,
        actions: dict[PlayerId, Action],
        players: list[Player],
    ) -> TransitionResult:
        """
        Resolve a set of simultaneously submitted actions.

        Called by the engine when all expected players have submitted their
        actions in a COMMIT_REVEAL or TIME_WINDOW phase.

        For players who didn't submit (timeout), the engine will have already
        applied the TimeoutBehavior and either:
        - Removed the player (LOSE_GAME)
        - Inserted a pass/skip action (FORCE_PASS)
        - Inserted a random valid action (RANDOM_ACTION)
        """
        ...

    # --- AI serialization ---

    def state_to_ai_view(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
        players: list[Player],
    ) -> dict:
        """
        Serialize game state for a bot. Same information as get_player_view but
        structured for machine consumption:
        - Use coordinate arrays instead of visual descriptions
        - Include valid action enumeration
        - Flatten nested structures where helpful
        - Include game-specific heuristic data (e.g. feature sizes)
        """
        ...

    def parse_ai_action(
        self,
        response: dict,
        phase: Phase,
        player_id: PlayerId,
    ) -> Action:
        """
        Parse a bot's response dict into an Action. Raise ValueError if
        the response is malformed.
        """
        ...

    # --- Optional hooks ---

    def on_player_disconnect(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
    ) -> dict | None:
        """
        Called when a player disconnects. Return modified game_data if the game
        needs to react (e.g. reveal their hand), or None to do nothing.
        Optional — default does nothing.
        """
        ...

    def get_spectator_summary(
        self,
        game_data: dict,
        phase: Phase,
        players: list[Player],
    ) -> dict:
        """
        Return a lightweight summary for the lobby/spectator list.
        E.g. {"turn": 15, "tiles_remaining": 30, "leader": "player-1"}
        Optional — default returns scores only.
        """
        ...
```

### 2.2 Validation Against Real Games

Let's walk through five games to verify the protocol handles them:

#### Carcassonne (tile placement, sequential)

```
Phases:
  1. "draw_tile"     → auto_resolve=True, engine triggers, game draws from bag
  2. "place_tile"    → SEQUENTIAL, current player, action: {x, y, rotation}
  3. "place_meeple"  → SEQUENTIAL, current player, action: {feature_id} or {skip: true}
  4. "score"         → auto_resolve=True, game checks completed features

Flow: draw_tile → place_tile → place_meeple → score → draw_tile (next player)
Game over: when tile bag is empty after scoring

Hidden info: tile bag contents (show count only), drawn tile (visible to all after draw)
Concurrent: never — pure sequential
```

Works cleanly. Each phase has exactly one expected action (or auto-resolves).

#### Caylus (multi-phase worker placement)

```
Phases (per round):
  1. "place_workers"  → SEQUENTIAL, players take turns placing 1 worker or passing
                        Phase loops: after each placement, next_phase points back
                        to "place_workers" until all have passed.
  2. "provost_move"   → SEQUENTIAL, specific player moves provost
  3. "activate_buildings" → auto_resolve=True for each building in order,
                           BUT some buildings require player input:
                           → "building_choice" → SEQUENTIAL, building's player
                           After choice, back to activate_buildings
  4. "build_castle"   → SEQUENTIAL, eligible players choose castle section
  5. "end_of_round"   → auto_resolve=True, cleanup

The KEY here: activate_buildings is a loop. Each building activation may or may
not require player input. The game plugin handles this by returning either:
  - next_phase = "activate_buildings" (continue to next building, auto_resolve)
  - next_phase = "building_choice" (need player input, then back to activate)
```

Works. The dynamic phase model handles Caylus's complex nested flow because
the game plugin controls the next_phase transition, not a fixed sequence.

#### 7 Wonders (simultaneous drafting)

```
Phases (per age):
  1. "choose_card"    → COMMIT_REVEAL, ALL players simultaneously
                        Each player picks a card from their hand.
  2. "resolve_cards"  → auto_resolve=True, apply chosen cards, rotate hands
  3. "military"       → auto_resolve=True (at end of age only)

The COMMIT_REVEAL mode means:
  - Engine sends action_required to all players
  - Players submit actions (hidden from each other)
  - Engine collects all, then calls resolve_concurrent_actions
  - Game applies all cards, produces events, returns next phase
```

Works. The commit-reveal concurrent mode is exactly what simultaneous
drafting needs.

#### Agricola (worker placement + harvest)

```
Phases:
  1. "place_worker"   → SEQUENTIAL, players alternate placing workers
                        Like Caylus, the phase loops until all workers placed.
  2. "resolve_actions" → auto_resolve=True, execute action spaces in order
                         Some need player choices (e.g. "which rooms to build"):
                         → "action_choice" sub-phase
  3. "harvest"        → SEQUENTIAL per player (field, feed, breed phases)
                        Each sub-step may need input:
                        → "harvest_feed" → player chooses how to feed family
                        → "harvest_breed" → player chooses which animals to keep

Harvest is complex because each player's harvest involves multiple decisions.
Modeled as: next_phase cycles through per-player harvest sub-phases.
```

Works. The phase model handles the recursive/looping nature of worker
placement and the multi-step harvest by chaining phases dynamically.

#### A trick-taking card game (e.g. Hearts)

```
Phases:
  1. "pass_cards"     → COMMIT_REVEAL, all players simultaneously choose 3 cards
  2. "play_trick"     → SEQUENTIAL, starting player leads, others follow in order
                        4 expected_actions, one per player.
  3. "score_trick"    → auto_resolve=True, determine trick winner
                        next_phase → "play_trick" (winner leads) or "score_round"
  4. "score_round"    → auto_resolve=True, tally points, check for game end

Hidden info: each player's hand (only see own cards)
```

Works. Mixed concurrent (pass) and sequential (tricks) in the same game.

### 2.3 Protocol Gaps Identified and Addressed

**Gap 1: Looping phases.** Some phases need to repeat (worker placement round-robin).
**Solution**: The game plugin returns `next_phase` pointing to the same phase name
with updated metadata (e.g. `metadata.next_player_index += 1`). The engine doesn't
care if the phase name repeats — it just processes whatever phase it receives.

**Gap 2: Variable number of expected actions.** In "place_workers", the number
of remaining actions depends on who has passed.
**Solution**: `expected_actions` is recalculated each time the phase transitions.
The game plugin knows who has passed (tracked in game_data) and only includes
non-passed players.

**Gap 3: Auto-resolve phases that sometimes need input.** Caylus's building
activation is auto-resolve *unless* a building requires a choice.
**Solution**: `auto_resolve=True` is a hint. The engine processes auto-resolve phases
by calling `apply_action` with a synthetic "system" action (action_type="auto_resolve").
If the game needs player input, it returns a next_phase with `auto_resolve=False`
and appropriate `expected_actions`. The engine seamlessly switches to waiting for
player input.

**Gap 4: Spectator delay.** Some games want spectators to see state with a delay
to prevent cheating (e.g. coaching).
**Solution**: `get_player_view(player_id=None)` returns the spectator view.
The engine can optionally apply a delay before broadcasting to spectators.
This is a server concern, not a game plugin concern.

---

## 3. Engine Core — The Orchestrator

The engine is the runtime that orchestrates game plugins. It's responsible for:
- Managing the action → validate → apply → broadcast loop
- Timer management
- Concurrent action collection and resolution
- Event persistence
- View generation and distribution

### 3.1 GameSession

```python
class GameSession:
    """
    Manages a single active game match. One GameSession per match.
    Lives in memory while the game is active; state is persisted to
    Redis (hot) and Postgres (durable).
    """

    def __init__(
        self,
        match_id: MatchId,
        plugin: GamePlugin,
        state: GameState,
        event_store: EventStore,       # Writes events to Postgres
        state_store: StateStore,       # Reads/writes state to Redis
        broadcaster: Broadcaster,      # Sends updates to WebSocket clients
        timer_manager: TimerManager,   # Manages per-player timers
    ):
        self.match_id = match_id
        self.plugin = plugin
        self.state = state
        self.event_store = event_store
        self.state_store = state_store
        self.broadcaster = broadcaster
        self.timer_manager = timer_manager
        self._lock = asyncio.Lock()    # Serialize state mutations

    async def handle_action(self, action: Action) -> None:
        """
        Main entry point: a player submitted an action.

        Flow:
        1. Validate envelope (is it this player's turn? correct action type?)
        2. Delegate to game plugin for rule validation
        3. Apply action (sequential) or buffer action (concurrent)
        4. Persist events
        5. Update state in Redis
        6. Broadcast updated views to all connected players
        7. Check for game over
        8. Advance to next phase if needed
        """
        async with self._lock:
            phase = self.state.current_phase

            # --- Envelope validation ---
            error = self._validate_envelope(action, phase)
            if error:
                await self.broadcaster.send_error(action.player_id, error)
                return

            # --- Concurrent mode: buffer or resolve ---
            if phase.concurrent_mode != ConcurrentMode.SEQUENTIAL:
                await self._handle_concurrent_action(action, phase)
                return

            # --- Sequential mode: validate + apply ---
            rule_error = self.plugin.validate_action(
                self.state.game_data, phase, action
            )
            if rule_error:
                await self.broadcaster.send_error(action.player_id, rule_error)
                return

            # Apply
            result = self.plugin.apply_action(
                self.state.game_data, phase, action, self.state.players
            )

            # Persist and broadcast
            await self._apply_result(result, action)

    async def _handle_concurrent_action(self, action: Action, phase: Phase) -> None:
        """Buffer action for concurrent phase; resolve when all are in."""
        # Validate
        rule_error = self.plugin.validate_action(
            self.state.game_data, phase, action
        )
        if rule_error:
            await self.broadcaster.send_error(action.player_id, rule_error)
            return

        # Buffer
        self.state.committed_actions[action.player_id] = action
        await self.broadcaster.send_action_committed(action.player_id)

        # Check if all expected players have committed
        expected_players = {
            ea.player_id for ea in phase.expected_actions
            if ea.player_id is not None
        }
        # If any expected_action has player_id=None, ALL players must commit
        if any(ea.player_id is None for ea in phase.expected_actions):
            expected_players = {p.player_id for p in self.state.players}

        if expected_players <= set(self.state.committed_actions.keys()):
            # All actions received — resolve
            result = self.plugin.resolve_concurrent_actions(
                self.state.game_data,
                phase,
                self.state.committed_actions,
                self.state.players,
            )
            self.state.committed_actions = {}
            await self._apply_result(result, source_action=None)

    async def _apply_result(
        self, result: TransitionResult, source_action: Action | None
    ) -> None:
        """Common path: persist events, update state, broadcast, check game over."""
        # Update state
        self.state.game_data = result.game_data
        self.state.scores = result.scores
        self.state.current_phase = result.next_phase
        self.state.action_number += 1

        # Persist events
        events_with_meta = []
        for event in result.events:
            persisted = PersistedEvent(
                match_id=self.match_id,
                sequence_number=self.state.action_number,
                event_type=event.event_type,
                player_id=event.player_id,
                payload=event.payload,
                timestamp=datetime.utcnow(),
            )
            events_with_meta.append(persisted)
        await self.event_store.append_events(events_with_meta)

        # Persist state to Redis
        await self.state_store.save_state(self.match_id, self.state)

        # Broadcast updated views to each player
        await self._broadcast_views()

        # Check game over
        if result.game_over:
            await self._finish_game(result.game_over)
            return

        # Handle auto-resolve phases
        if result.next_phase.auto_resolve:
            await self._auto_resolve_phase()
        else:
            # Start timer for next expected player
            await self._start_turn_timer()

    async def _auto_resolve_phase(self) -> None:
        """Process an auto-resolve phase (no player input needed)."""
        synthetic_action = Action(
            action_type="auto_resolve",
            player_id=PlayerId("system"),
            payload={},
            timestamp=datetime.utcnow(),
        )
        result = self.plugin.apply_action(
            self.state.game_data,
            self.state.current_phase,
            synthetic_action,
            self.state.players,
        )
        await self._apply_result(result, source_action=synthetic_action)

    async def _broadcast_views(self) -> None:
        """Send each connected player their filtered view."""
        for player in self.state.players:
            game_view = self.plugin.get_player_view(
                self.state.game_data,
                self.state.current_phase,
                player.player_id,
                self.state.players,
            )
            valid_actions = self.plugin.get_valid_actions(
                self.state.game_data,
                self.state.current_phase,
                player.player_id,
            )
            view = PlayerView(
                match_id=self.state.match_id,
                game_id=self.state.game_id,
                players=self.state.players,
                current_phase=self.state.current_phase,
                status=self.state.status,
                turn_number=self.state.turn_number,
                scores=self.state.scores,
                player_timers=self.state.player_timers,
                game_data=game_view,
                valid_actions=valid_actions,
                viewer_id=player.player_id,
                is_spectator=False,
            )
            await self.broadcaster.send_state_update(player.player_id, view)

        # Spectator view
        spectator_view_data = self.plugin.get_player_view(
            self.state.game_data,
            self.state.current_phase,
            None,
            self.state.players,
        )
        spectator_view = PlayerView(
            match_id=self.state.match_id,
            game_id=self.state.game_id,
            players=self.state.players,
            current_phase=self.state.current_phase,
            status=self.state.status,
            turn_number=self.state.turn_number,
            scores=self.state.scores,
            player_timers=self.state.player_timers,
            game_data=spectator_view_data,
            valid_actions=[],
            viewer_id=None,
            is_spectator=True,
        )
        await self.broadcaster.send_spectator_update(spectator_view)

    def _validate_envelope(self, action: Action, phase: Phase) -> str | None:
        """Check that the action is structurally valid in the current context."""
        if self.state.status != GameStatus.ACTIVE:
            return "Game is not active"

        # Check action type matches an expected action
        matching = [
            ea for ea in phase.expected_actions
            if ea.action_type == action.action_type
            and (ea.player_id is None or ea.player_id == action.player_id)
        ]
        if not matching:
            return f"Unexpected action '{action.action_type}' from player '{action.player_id}'"

        # For concurrent phases, check player hasn't already committed
        if phase.concurrent_mode != ConcurrentMode.SEQUENTIAL:
            if action.player_id in self.state.committed_actions:
                return "You have already submitted your action for this phase"

        return None

    async def _start_turn_timer(self) -> None:
        """Start the timer for the current player(s)."""
        for ea in self.state.current_phase.expected_actions:
            if ea.player_id and ea.player_id in self.state.player_timers:
                await self.timer_manager.start_timer(
                    self.match_id,
                    ea.player_id,
                    self.state.player_timers[ea.player_id],
                    callback=lambda pid=ea.player_id: self._on_timeout(pid),
                )

    async def _on_timeout(self, player_id: PlayerId) -> None:
        """Handle a player's timer running out."""
        async with self._lock:
            behavior = self.state.config.timer.timeout_behavior

            if behavior == TimeoutBehavior.LOSE_GAME:
                result = GameResult(
                    winners=[p.player_id for p in self.state.players if p.player_id != player_id],
                    final_scores=self.state.scores,
                    reason="timeout",
                )
                await self._finish_game(result)

            elif behavior == TimeoutBehavior.LOSE_TURN:
                # Advance to next phase with a synthetic "pass" action
                pass_action = Action(
                    action_type=self.state.current_phase.expected_actions[0].action_type,
                    player_id=player_id,
                    payload={"forced_pass": True},
                    timestamp=datetime.utcnow(),
                )
                # Game plugin should handle forced_pass in payload
                result = self.plugin.apply_action(
                    self.state.game_data,
                    self.state.current_phase,
                    pass_action,
                    self.state.players,
                )
                await self._apply_result(result, pass_action)

            elif behavior == TimeoutBehavior.RANDOM_ACTION:
                valid = self.plugin.get_valid_actions(
                    self.state.game_data,
                    self.state.current_phase,
                    player_id,
                )
                if valid:
                    import random
                    chosen = random.choice(valid)
                    random_action = Action(
                        action_type=self.state.current_phase.expected_actions[0].action_type,
                        player_id=player_id,
                        payload=chosen,
                        timestamp=datetime.utcnow(),
                    )
                    await self.handle_action(random_action)

            elif behavior == TimeoutBehavior.FORCE_PASS:
                pass_action = Action(
                    action_type="pass",
                    player_id=player_id,
                    payload={},
                    timestamp=datetime.utcnow(),
                )
                await self.handle_action(pass_action)

    async def _finish_game(self, result: GameResult) -> None:
        """Finalize a completed game."""
        self.state.status = GameStatus.FINISHED
        await self.state_store.save_state(self.match_id, self.state)
        await self.broadcaster.send_game_over(result)
        await self.timer_manager.cancel_all(self.match_id)
        # Trigger async post-game tasks (ranking update, cleanup Redis)
```

### 3.2 Session Lifecycle

```
1. Room created → GameSession NOT yet created
2. All players ready → Engine:
   a. Load game plugin by game_id
   b. Call plugin.create_initial_state()
   c. Create GameState with engine fields + game_data
   d. Create GameSession
   e. Persist initial state + setup events
   f. Broadcast initial PlayerViews
   g. If first phase is auto_resolve, process it immediately
   h. Start timer for first player

3. During play → GameSession.handle_action() loop

4. Game over → _finish_game():
   a. Persist final state
   b. Update rankings (async task)
   c. Cleanup Redis hot state (after cooldown for reconnects)
   d. GameSession can be garbage collected
```

---

## 4. Event Sourcing

### 4.1 Persisted Event Schema

```python
class PersistedEvent(BaseModel):
    """Event as stored in PostgreSQL."""
    id: int                          # Auto-increment PK
    match_id: MatchId
    sequence_number: int             # Per-match monotonic counter
    event_type: str
    player_id: PlayerId | None
    payload: dict                    # JSONB
    timestamp: datetime

    class Config:
        # Index: (match_id, sequence_number) UNIQUE
        # Index: (match_id, event_type) for filtering
        pass
```

### 4.2 Determinism Contract

For event sourcing to work, replaying the same events from the same initial
state must produce the same result. This requires:

1. **No external randomness in apply_action.** All randomness (shuffles, draws)
   must come from a seeded RNG stored in `game_data`. Example:
   ```python
   # In game_data:
   {"rng_state": [seed_bytes], "tile_bag": [pre_shuffled_tiles], ...}
   ```
   The RNG is seeded at `create_initial_state` using `config.random_seed`.

2. **No dependency on wall clock time.** Timestamps are metadata only, not
   used in game logic.

3. **No dependency on action ordering within concurrent phases.** The
   `resolve_concurrent_actions` method receives all actions as a dict — the
   game must produce the same result regardless of submission order.

### 4.3 State Reconstruction

```python
async def reconstruct_state_at(
    match_id: MatchId,
    target_sequence: int | None = None,  # None = latest
) -> GameState:
    """
    Rebuild game state by replaying events from the initial state.

    Used for:
    - Replays
    - Server restart recovery
    - Debugging
    """
    # Load match metadata and game plugin
    match = await match_store.get_match(match_id)
    plugin = plugin_registry.get(match.game_id)

    # Recreate initial state (deterministic from seed + players)
    config = match.config
    players = match.players
    game_data, first_phase, _ = plugin.create_initial_state(players, config)

    state = GameState(
        match_id=match_id,
        game_id=match.game_id,
        players=players,
        current_phase=first_phase,
        status=GameStatus.ACTIVE,
        config=config,
        game_data=game_data,
    )

    # Replay events
    events = await event_store.get_events(
        match_id, up_to_sequence=target_sequence
    )

    for event in events:
        # Convert event back to action and apply
        # (events store enough info to reconstruct the action)
        action = _event_to_action(event)
        if state.current_phase.auto_resolve:
            result = plugin.apply_action(
                state.game_data, state.current_phase,
                Action(action_type="auto_resolve", player_id=PlayerId("system"), payload={}),
                state.players,
            )
        else:
            result = plugin.apply_action(
                state.game_data, state.current_phase, action, state.players
            )
        state.game_data = result.game_data
        state.scores = result.scores
        state.current_phase = result.next_phase

    return state
```

### 4.4 Snapshots (Optimization)

For long games, replaying from event 0 is slow. Periodic snapshots help:

```
Every N actions (e.g. N=50), persist a full GameState snapshot.
To reconstruct at event 300: load snapshot at event 250, replay events 251-300.
```

Snapshots are stored in a separate table:

```sql
game_snapshots (
    match_id,
    sequence_number,
    state_json JSONB,
    created_at
)
-- Index: (match_id, sequence_number)
```

This is a **performance optimization only** — the event log remains the source
of truth. Snapshots can be regenerated from events at any time.

---

## 5. Concurrent Play Resolution

### 5.1 Commit-Reveal Flow

```
1. Engine enters a COMMIT_REVEAL phase
2. Engine sends all players: { type: "action_required", concurrent: true }
3. Each player submits an action
4. Engine stores action in committed_actions (hidden from other players)
5. Engine sends submitter: { type: "action_committed" }
6. Engine sends all: { type: "players_committed", committed: ["player-1"] }
   (Other players see WHO committed but not WHAT)
7. When all expected players have committed:
   a. Engine calls plugin.resolve_concurrent_actions(all_actions)
   b. Engine broadcasts reveal: all actions + resolution events
   c. Transition to next phase

Timeout handling:
  If a player doesn't commit within the time limit, apply TimeoutBehavior
  BEFORE resolving (insert a pass/random/forfeit for that player).
```

### 5.2 Time-Window Flow

```
1. Engine enters a TIME_WINDOW phase
2. Engine sends all players: { type: "action_required", window_ms: 30000 }
3. Actions are collected for the duration of the window
4. When window expires (or all players have submitted):
   a. Apply TimeoutBehavior for missing players
   b. Call plugin.resolve_concurrent_actions(all_actions)
   c. Broadcast results
   d. Transition to next phase

The difference from commit-reveal: there's no "locked in" confirmation.
Players can potentially revise their action within the window (game-configurable).
```

### 5.3 Engine Responsibility Matrix

| Concern | Engine | Game Plugin |
|---|---|---|
| Collecting actions | Yes | No |
| Hiding committed actions | Yes | No |
| Timeout enforcement | Yes | No |
| Timeout behavior (what action to insert) | Yes (generic) | Can override via forced_pass handling |
| Resolving concurrent actions | No | Yes |
| Broadcasting reveals | Yes | No |
| Determining concurrent mode | No | Yes (via phase) |

---

## 6. Timer Integration

### 6.1 Timer Manager

```python
class TimerManager:
    """
    Manages per-player timers using Redis for persistence and async
    callbacks for timeout handling.

    Timer state is stored in Redis so it survives server restarts.
    The manager uses asyncio tasks for countdown; on restart, it
    reloads active timers from Redis.
    """

    async def start_timer(
        self,
        match_id: MatchId,
        player_id: PlayerId,
        remaining_ms: int,
        callback: Callable,
    ) -> None:
        """Start countdown for a player. Calls callback on expiry."""
        ...

    async def pause_timer(self, match_id: MatchId, player_id: PlayerId) -> int:
        """Pause and return remaining ms. Used on player action / disconnect."""
        ...

    async def apply_increment(
        self, match_id: MatchId, player_id: PlayerId, increment_ms: int
    ) -> None:
        """Add time (Fischer increment after a move)."""
        ...

    async def cancel_all(self, match_id: MatchId) -> None:
        """Cancel all timers for a match (game over)."""
        ...

    async def get_remaining(self, match_id: MatchId) -> dict[PlayerId, int]:
        """Get all players' remaining time."""
        ...
```

### 6.2 Timer Flow During a Turn

```
1. Player's turn starts → timer_manager.start_timer(player, remaining_ms)
2. Timer ticks → periodic timer_update messages to all clients (every 1s)
3. Player submits action:
   a. timer_manager.pause_timer(player) → get remaining_ms
   b. If FISCHER: timer_manager.apply_increment(player, increment_ms)
   c. Update state.player_timers[player] = remaining_ms (+ increment)
   d. Apply action normally
4. Timeout fires (remaining hits 0):
   a. Callback → GameSession._on_timeout(player)
   b. Apply TimeoutBehavior
```

### 6.3 Timer Persistence in Redis

```
Key: timer:{match_id}:{player_id}
Value: { remaining_ms: int, started_at: timestamp, is_running: bool }

On server restart:
  - Load all active timer keys
  - Calculate elapsed = now - started_at
  - Remaining = remaining_ms - elapsed
  - If remaining <= 0: trigger timeout
  - Else: restart timer with adjusted remaining
```

---

## 7. Game Plugin Registration & Discovery

### 7.1 Plugin Registry (gRPC-based)

Game plugins are implemented in the Rust engine and discovered at startup
via gRPC. The Python `PluginRegistry` connects to the Rust engine, calls
`ListGames()`, and registers a `GrpcGamePlugin` adapter for each game.

```python
class PluginRegistry:
    """Registers game plugins provided by the Rust engine via gRPC."""

    def __init__(self):
        self._plugins: dict[str, GamePlugin] = {}

    def register(self, plugin: GamePlugin) -> None:
        game_id = plugin.game_id
        if game_id in self._plugins:
            raise ValueError(f"Game '{game_id}' already registered")
        self._plugins[game_id] = plugin

    def get(self, game_id: str) -> GamePlugin:
        if game_id not in self._plugins:
            raise KeyError(f"Unknown game: {game_id}")
        return self._plugins[game_id]

    def list_games(self) -> list[dict]:
        return [
            {
                "game_id": p.game_id,
                "display_name": p.display_name,
                "min_players": p.min_players,
                "max_players": p.max_players,
                "description": p.description,
            }
            for p in self._plugins.values()
        ]

    def connect_grpc(self, address: str, max_retries: int = 30, retry_delay: float = 2.0) -> None:
        """Connect to the Rust game engine via gRPC and register all available games.

        Retries on failure to handle the case where the game engine is still starting up.
        """
        from src.engine.grpc_plugin import connect_grpc

        for attempt in range(1, max_retries + 1):
            try:
                plugins = connect_grpc(address)
                for plugin in plugins:
                    self.register(plugin)
                return
            except Exception as e:
                if attempt == max_retries:
                    raise
                time.sleep(retry_delay)
```

The `GrpcGamePlugin` adapter implements the `GamePlugin` protocol by
delegating every method call to the Rust engine via gRPC. Game state is
serialized as JSON across the boundary. See `backend/src/engine/grpc_plugin.py`.

### 7.2 Adding a New Game

To add a new game to the platform:

1. **Implement the `TypedGamePlugin` trait in Rust** (`game-engine/src/games/<game_name>/`)
2. **Register the game in the Rust gRPC server** (`game-engine/src/server.rs`)
3. **Add frontend components** (`frontend/src/components/games/<game_name>/`)

The Python backend requires no changes — new games are discovered automatically
via the `ListGames` gRPC call at startup.

### 7.3 Plugin Validation

On registration, the engine can validate the plugin via `validation.py`:

```python
def validate_plugin(plugin: GamePlugin) -> list[str]:
    """
    Run sanity checks on a plugin to catch common errors early.
    Returns list of warnings/errors.
    """
    # Checks required attributes, tests create_initial_state with min players,
    # verifies get_valid_actions and get_player_view don't crash,
    # and verifies determinism (same seed → same state).
```

---

## 8. Error Handling

### 8.1 Error Types

```python
class GameEngineError(Exception):
    """Base class for engine errors."""
    pass

class InvalidActionError(GameEngineError):
    """Action is not valid in current state."""
    def __init__(self, message: str, action: Action):
        self.message = message
        self.action = action

class GameNotActiveError(GameEngineError):
    """Action submitted to a non-active game."""
    pass

class NotYourTurnError(GameEngineError):
    """Player tried to act when it's not their turn."""
    pass

class PluginError(GameEngineError):
    """Game plugin raised an unexpected error."""
    def __init__(self, message: str, original: Exception):
        self.message = message
        self.original = original
```

### 8.2 Error Communication

Errors are sent to the client via WebSocket:

```json
{
    "type": "error",
    "code": "invalid_action",
    "message": "Cannot place tile here: edges don't match adjacent tiles",
    "details": {
        "attempted_action": { "type": "place_tile", "payload": { "x": 3, "y": -1, "rotation": 90 } }
    }
}
```

Error codes:
- `invalid_action` — Action violates game rules
- `not_your_turn` — Wrong player
- `game_not_active` — Game is over/paused
- `action_type_mismatch` — Wrong action type for current phase
- `already_committed` — Already submitted in concurrent phase
- `internal_error` — Unexpected server error (logged, not detailed to client)

---

## 9. Edge Cases

### 9.1 Player Disconnection

```
1. WebSocket closes → broadcaster detects disconnect
2. Engine:
   a. Start grace period (configurable, e.g. 60s for reconnect)
   b. Pause player's timer
   c. Broadcast { type: "player_disconnected", player_id: ... } to others
   d. Call plugin.on_player_disconnect() if implemented
3. Player reconnects within grace period:
   a. Restore WebSocket, send current PlayerView
   b. Resume timer
   c. Broadcast { type: "player_reconnected", player_id: ... }
4. Grace period expires:
   a. Apply timeout behavior for current action (if it's their turn)
   b. If it's NOT their turn, just mark as disconnected — they'll timeout
      when their turn comes
   c. If ALL humans disconnect, pause the game entirely
```

### 9.2 Server Restart Recovery

```
1. On startup, scan Redis for active game states
2. For each active game:
   a. Load GameState from Redis
   b. Load plugin, create GameSession
   c. Recalculate timers (elapsed = now - last_saved)
   d. Wait for players to reconnect via WebSocket
   e. Resume game
3. If Redis is empty but Postgres has active games:
   a. Reconstruct state from event log (slower but correct)
```

### 9.3 Spectator Joining Mid-Game

```
1. Spectator connects to WebSocket with spectator flag
2. Engine sends current spectator view (no hidden info)
3. Spectator receives all subsequent state_update broadcasts
4. Spectator cannot submit actions (envelope validation rejects)
```

### 9.4 Game Abandonment

```
If a player disconnects and doesn't return within the grace period,
AND it's a multi-player game (not vs AI):
  - If 2-player: other player wins by forfeit
  - If 3+ players: disconnected player's pieces/resources become neutral
    (game-plugin-specific handling via on_player_disconnect)
  - Game may continue with remaining players or be abandoned
    (configurable per game)
```

---

## 10. Module Structure

```
backend/src/engine/
├── __init__.py
├── models.py          # All data models (GameState, Phase, Action, Event, etc.)
├── protocol.py        # GamePlugin protocol definition (contract for gRPC adapter)
├── grpc_plugin.py     # GrpcGamePlugin — adapter delegating to Rust via gRPC
├── session.py         # GameSession orchestrator
├── session_manager.py # Manages all active sessions, handles recovery
├── registry.py        # PluginRegistry (discovers games from Rust engine via gRPC)
├── event_store.py     # EventStore (Postgres append-only event log)
├── state_store.py     # StateStore (Redis hot state cache)
├── bot_runner.py      # Schedules and executes bot moves
├── bot_strategy.py    # BotStrategy protocol + RandomStrategy + GrpcMctsStrategy
├── errors.py          # Error types
├── validation.py      # Plugin validation utilities
└── proto/             # Generated protobuf/gRPC stubs
    ├── game_engine_pb2.py
    └── game_engine_pb2_grpc.py

game-engine/src/       # Rust game engine (gRPC server)
├── engine/
│   ├── mcts.rs        # Game-agnostic MCTS (UCT, progressive widening, RAVE)
│   ├── simulator.rs   # Action application and auto-resolve loop
│   ├── arena.rs       # Bot-vs-bot arena runner
│   ├── bot_strategy.rs # Strategy trait, MctsStrategy, RandomStrategy
│   ├── evaluator.rs   # Heuristic evaluator trait
│   └── plugin.rs      # TypedGamePlugin trait
├── games/
│   ├── carcassonne/   # Carcassonne (board, tiles, features, scoring, evaluator)
│   └── tictactoe/     # TicTacToe (MCTS isolation testing)
└── server.rs          # gRPC server (tonic)
```

---

## Appendix: Summary of Key Design Decisions

| Decision | Rationale |
|---|---|
| Phases are dynamic, not a fixed list | Complex games (Caylus) have conditional phase transitions |
| game_data is opaque dict | Engine doesn't need to understand game-specific state |
| Actions and Events are distinct | Action = intent (may fail), Event = fact (what happened) |
| GamePlugin methods are pure functions | Required for deterministic replay from event log |
| Timer managed by engine, not plugin | Separation of concerns; timer is infrastructure |
| Single async lock per GameSession | Prevents race conditions on state mutation; fine for single-server |
| Auto-resolve phases use synthetic actions | Unifies the action→event pipeline for all transitions |
| Random seed stored in config | Enables reproducible games for replay and testing |
