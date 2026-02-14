# 07 — Replay & Ranking Systems

---

## Part A: Replay System

Built on event sourcing. Every game action produces events that are persisted
to PostgreSQL. Replays reconstruct state by replaying events.

### 1. Event Storage

#### 1.1 Schema

```sql
CREATE TABLE game_events (
    id BIGSERIAL PRIMARY KEY,
    match_id UUID NOT NULL REFERENCES matches(id),
    sequence_number INT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    player_id UUID,
    payload JSONB NOT NULL DEFAULT '{}',
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (match_id, sequence_number)
);

CREATE INDEX idx_game_events_match_seq ON game_events (match_id, sequence_number);
CREATE INDEX idx_game_events_match_type ON game_events (match_id, event_type);
```

#### 1.2 Storage Estimates

Per Carcassonne game (~72 tiles, ~2 events per tile on average):
- ~150 events per game
- ~500 bytes average per event (JSON payload)
- ~75 KB per game

At 1000 games/day (ambitious): ~75 MB/day, ~2.2 GB/month.
Well within VPS storage. No pruning needed for years.

#### 1.3 Write Path

Events are written in the `_apply_result` method of GameSession:

```python
async def append_events(self, events: list[PersistedEvent]) -> None:
    """Batch insert events. Called after each action."""
    async with self.db.begin():
        await self.db.execute(
            insert(GameEvent),
            [e.model_dump() for e in events],
        )
```

Events are append-only. Never updated or deleted (during normal operation).

### 2. Replay API

#### 2.1 Full Replay

```
GET /api/v1/matches/{match_id}/replay

Response:
{
  "match": {
    "id": "uuid",
    "game_id": "carcassonne",
    "players": [...],
    "config": {...},
    "started_at": "...",
    "ended_at": "...",
    "result": {...}
  },
  "events": [
    {
      "sequence_number": 1,
      "event_type": "game_started",
      "player_id": null,
      "payload": {"players": [...]},
      "timestamp": "..."
    },
    {
      "sequence_number": 2,
      "event_type": "tile_drawn",
      "player_id": "p1",
      "payload": {"tile": "D", "tiles_remaining": 70},
      "timestamp": "..."
    },
    ...
  ]
}
```

For typical games (~150 events), the full replay fits in a single response
(<100 KB). No pagination needed.

#### 2.2 Paginated Events (For Very Long Games)

```
GET /api/v1/matches/{match_id}/events?from_seq=0&limit=50

Response:
{
  "events": [...],
  "next_cursor": 50,
  "total_events": 148
}
```

#### 2.3 State at Specific Event

For the replay viewer's seek functionality:

```
GET /api/v1/matches/{match_id}/state-at/{sequence_number}

Response:
{
  "sequence_number": 42,
  "game_data": { ... },  // Public view at this point
  "phase": "place_tile",
  "scores": {...},
  "turn_number": 14
}
```

This endpoint reconstructs state server-side by replaying events up to the
target sequence number. Caching strategy:
- Cache the response for completed games (immutable)
- Use periodic snapshots for fast reconstruction (see 01-game-engine.md §4.4)

### 3. Replay Viewer (Client)

See 03-frontend.md §5 for the full frontend design. Summary:

```
ReplayViewer
├── GameRenderer (same as live game, but read-only)
├── ReplayControls
│   ├── PlayButton (auto-advance with configurable speed)
│   ├── StepForward / StepBackward
│   ├── SeekBar (slider to jump to any event)
│   └── SpeedControl (1x, 2x, 4x)
├── EventLog (scrollable list of events with descriptions)
└── ScoreGraph (line chart of scores over time)
```

State reconstruction for the replay viewer uses the server endpoint
(`/state-at/{seq}`) to avoid reimplementing game logic in TypeScript.
The viewer requests state when the user seeks, with debouncing for
smooth slider interaction.

### 4. Sharing & Public Replays

All completed games are publicly viewable by default.

```
Public URL: https://meeple.cat/replay/{match_id}

OG meta tags for social sharing:
  og:title = "Carcassonne — Alice vs Bob"
  og:description = "Alice wins 102-85. Watch the full replay."
  og:image = server-rendered board snapshot (future enhancement)
```

Users can link to a specific moment:
```
https://meeple.cat/replay/{match_id}?t=42  (event 42)
```

### 5. Annotated Replays (Future)

Allow users or AI to add commentary to specific events:

```sql
CREATE TABLE replay_annotations (
    id SERIAL PRIMARY KEY,
    match_id UUID NOT NULL REFERENCES matches(id),
    sequence_number INT NOT NULL,
    author_id UUID REFERENCES users(id),  -- NULL for AI annotations
    content TEXT NOT NULL,
    annotation_type VARCHAR(20) DEFAULT 'comment',  -- 'comment', 'highlight', 'mistake'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Not in V1 scope, but the schema is cheap to add later.

---

## Part B: Ranking System

### 6. Algorithm: Glicko-2

**Why Glicko-2 over ELO**:
- Tracks rating uncertainty (deviation) — new players have wide uncertainty
- Handles inactivity (deviation increases over time)
- Better calibrated for players with few games
- Widely used (Lichess, chess.com use variants of Glicko)

**Why not TrueSkill**:
- TrueSkill is Microsoft-patented (may have licensing issues)
- Designed for team games (overkill for 1v1 board games)
- Glicko-2 works fine for multiplayer free-for-all with minor adaptations

### 7. Rating Model

```python
from dataclasses import dataclass

@dataclass
class Rating:
    mu: float = 1500.0           # Rating (display value)
    phi: float = 350.0           # Rating deviation (uncertainty)
    sigma: float = 0.06          # Rating volatility

    @property
    def display_rating(self) -> int:
        """Conservative rating estimate (mu - 2*phi)."""
        return max(0, round(self.mu - 2 * self.phi))

    @property
    def is_provisional(self) -> bool:
        """High uncertainty = not enough games played."""
        return self.phi > 150
```

### 7.1 Database Schema

```sql
CREATE TABLE player_ratings (
    user_id UUID NOT NULL REFERENCES users(id),
    game_id VARCHAR(50) NOT NULL,
    mu FLOAT NOT NULL DEFAULT 1500.0,
    phi FLOAT NOT NULL DEFAULT 350.0,
    sigma FLOAT NOT NULL DEFAULT 0.06,
    games_played INT NOT NULL DEFAULT 0,
    wins INT NOT NULL DEFAULT 0,
    losses INT NOT NULL DEFAULT 0,
    draws INT NOT NULL DEFAULT 0,
    last_played TIMESTAMPTZ,

    PRIMARY KEY (user_id, game_id)
);

CREATE INDEX idx_ratings_game_mu ON player_ratings (game_id, mu DESC);
-- For leaderboard queries: ORDER BY mu DESC WHERE game_id = ?

-- Rating history for charts
CREATE TABLE rating_history (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    game_id VARCHAR(50) NOT NULL,
    match_id UUID NOT NULL REFERENCES matches(id),
    mu_before FLOAT NOT NULL,
    mu_after FLOAT NOT NULL,
    phi_before FLOAT NOT NULL,
    phi_after FLOAT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_rating_history_user_game ON rating_history (user_id, game_id, timestamp);
```

### 8. Rating Calculation

#### 8.1 When Ratings Update

Ratings update **after each completed game** (not abandoned games).
The update is triggered as an async task after `_finish_game()`.

#### 8.2 Two-Player Games

Standard Glicko-2 formula:

```python
import math

def update_ratings_2p(winner: Rating, loser: Rating, draw: bool = False) -> tuple[Rating, Rating]:
    """Update ratings for a 2-player game using Glicko-2."""
    # Step 1: Convert to Glicko-2 scale
    MU_SCALE = 173.7178
    winner_mu2 = (winner.mu - 1500) / MU_SCALE
    winner_phi2 = winner.phi / MU_SCALE
    loser_mu2 = (loser.mu - 1500) / MU_SCALE
    loser_phi2 = loser.phi / MU_SCALE

    # Step 2: Compute g(phi) and E(mu, mu_j, phi_j)
    def g(phi):
        return 1 / math.sqrt(1 + 3 * phi**2 / math.pi**2)

    def E(mu, mu_j, phi_j):
        return 1 / (1 + math.exp(-g(phi_j) * (mu - mu_j)))

    # Step 3: Compute variance and delta
    g_loser = g(loser_phi2)
    E_winner = E(winner_mu2, loser_mu2, loser_phi2)
    score_winner = 0.5 if draw else 1.0

    v_winner = 1 / (g_loser**2 * E_winner * (1 - E_winner))
    delta_winner = v_winner * g_loser * (score_winner - E_winner)

    # Symmetric for loser
    g_winner = g(winner_phi2)
    E_loser = E(loser_mu2, winner_mu2, winner_phi2)
    score_loser = 0.5 if draw else 0.0

    v_loser = 1 / (g_winner**2 * E_loser * (1 - E_loser))
    delta_loser = v_loser * g_winner * (score_loser - E_loser)

    # Step 4: Update volatility (simplified — full Glicko-2 uses iterative method)
    new_sigma_winner = _compute_new_sigma(winner.sigma, winner_phi2, v_winner, delta_winner)
    new_sigma_loser = _compute_new_sigma(loser.sigma, loser_phi2, v_loser, delta_loser)

    # Step 5: Update phi and mu
    phi_star_w = math.sqrt(winner_phi2**2 + new_sigma_winner**2)
    new_phi_w = 1 / math.sqrt(1/phi_star_w**2 + 1/v_winner)
    new_mu_w = winner_mu2 + new_phi_w**2 * g_loser * (score_winner - E_winner)

    phi_star_l = math.sqrt(loser_phi2**2 + new_sigma_loser**2)
    new_phi_l = 1 / math.sqrt(1/phi_star_l**2 + 1/v_loser)
    new_mu_l = loser_mu2 + new_phi_l**2 * g_winner * (score_loser - E_loser)

    # Convert back to Glicko scale
    return (
        Rating(mu=new_mu_w * MU_SCALE + 1500, phi=new_phi_w * MU_SCALE, sigma=new_sigma_winner),
        Rating(mu=new_mu_l * MU_SCALE + 1500, phi=new_phi_l * MU_SCALE, sigma=new_sigma_loser),
    )
```

#### 8.3 Multiplayer Games (3+ Players)

Glicko-2 is designed for 1v1. For multiplayer free-for-all games,
decompose into pairwise results:

```python
def update_ratings_multiplayer(
    results: list[tuple[str, Rating, float]],  # (player_id, rating, score)
) -> dict[str, Rating]:
    """
    Update ratings for a multiplayer game.

    Approach: each pair of players is treated as an independent match.
    The player with the higher score "wins" the pairwise comparison.
    Each player's rating is updated based on all pairwise outcomes.

    This is the approach used by multiplayer Glicko implementations.
    """
    # Sort by score descending
    sorted_results = sorted(results, key=lambda x: x[2], reverse=True)
    updates: dict[str, list[Rating]] = {pid: [] for pid, _, _ in results}

    for i in range(len(sorted_results)):
        for j in range(i + 1, len(sorted_results)):
            pid_a, rating_a, score_a = sorted_results[i]
            pid_b, rating_b, score_b = sorted_results[j]

            if score_a > score_b:
                new_a, new_b = update_ratings_2p(rating_a, rating_b, draw=False)
            elif score_a == score_b:
                new_a, new_b = update_ratings_2p(rating_a, rating_b, draw=True)
            else:
                new_b, new_a = update_ratings_2p(rating_b, rating_a, draw=False)

            updates[pid_a].append(new_a)
            updates[pid_b].append(new_b)

    # Average the pairwise updates for each player
    final = {}
    for pid, rating_updates in updates.items():
        if rating_updates:
            avg_mu = sum(r.mu for r in rating_updates) / len(rating_updates)
            avg_phi = sum(r.phi for r in rating_updates) / len(rating_updates)
            avg_sigma = sum(r.sigma for r in rating_updates) / len(rating_updates)
            final[pid] = Rating(mu=avg_mu, phi=avg_phi, sigma=avg_sigma)

    return final
```

### 9. Leaderboards

#### 9.1 Query Patterns

```sql
-- Top 25 for a game
SELECT u.id, u.display_name, u.avatar_url,
       r.mu, r.phi, r.games_played, r.wins, r.losses
FROM player_ratings r
JOIN users u ON u.id = r.user_id
WHERE r.game_id = 'carcassonne'
  AND r.games_played >= 10          -- Minimum games to appear
  AND r.phi < 150                   -- Exclude provisional ratings
ORDER BY r.mu DESC
LIMIT 25 OFFSET 0;

-- Player's rank in a game
SELECT COUNT(*) + 1 AS rank
FROM player_ratings
WHERE game_id = 'carcassonne'
  AND mu > (SELECT mu FROM player_ratings WHERE user_id = ? AND game_id = 'carcassonne')
  AND games_played >= 10
  AND phi < 150;
```

#### 9.2 Caching

Leaderboards are cached in Redis with a 5-minute TTL:

```python
LEADERBOARD_CACHE_TTL = 300  # 5 minutes

async def get_leaderboard(game_id: str, page: int, page_size: int) -> LeaderboardResponse:
    cache_key = f"leaderboard:{game_id}:{page}:{page_size}"
    cached = await redis.get(cache_key)
    if cached:
        return LeaderboardResponse.model_validate_json(cached)

    # Query DB
    result = await _query_leaderboard(game_id, page, page_size)
    await redis.setex(cache_key, LEADERBOARD_CACHE_TTL, result.model_dump_json())
    return result
```

### 10. Provisional Ratings

New players have high deviation (phi=350). They are:
- **Not shown on leaderboards** until phi < 150 (~10-15 games)
- **Shown with a "?" badge** in their profile
- **Matched more broadly** in matchmaking (wider rating range)

After each game, phi decreases. It converges toward ~50-80 after ~20-30 games.

### 11. Inactivity Decay

Glicko-2 naturally handles this: phi increases over time when a player
doesn't play. This is done during rating periods.

```python
def apply_rating_period_decay(rating: Rating, periods_inactive: int) -> Rating:
    """Increase uncertainty for inactive players."""
    new_phi = min(350, math.sqrt(rating.phi**2 + rating.sigma**2 * periods_inactive))
    return Rating(mu=rating.mu, phi=new_phi, sigma=rating.sigma)
```

A rating period = 1 week. Run a weekly cron job to decay ratings for players
who haven't played.

### 12. Anti-Abuse

#### 12.1 Smurfing

- Account linking by email reduces alt accounts
- Provisional period means smurfs must play ~15 games before appearing on leaderboards
- Report system (future) for suspicious accounts

#### 12.2 Sandbagging (Intentionally Losing to Lower Rating)

- Detect patterns: player with many losses followed by many wins
- Flag for review if win rate is suspiciously volatile
- For V1: not a priority (small community)

#### 12.3 Win Trading

- Detect repeated matchups between same players with alternating wins
- Flag for review
- For V1: not a priority

#### 12.4 Rated vs Unrated Games

Games are rated by default. Users can create unrated rooms (timer: NONE,
casual games). Unrated games don't affect ratings.

A game is rated if:
- Both/all players have accounts (not bots, unless bot ratings are enabled)
- Timer is not NONE
- Game completes normally (not abandoned)
- Game has at least a minimum number of moves (prevents instant resign farming)

### 13. Seasonal Rankings (Future)

Not in V1, but the schema supports it:

```sql
CREATE TABLE seasons (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),           -- "Season 1 - Winter 2025"
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_active BOOLEAN DEFAULT FALSE
);

CREATE TABLE seasonal_ratings (
    user_id UUID NOT NULL,
    game_id VARCHAR(50) NOT NULL,
    season_id INT NOT NULL REFERENCES seasons(id),
    final_mu FLOAT,
    final_phi FLOAT,
    games_played INT,
    peak_mu FLOAT,
    PRIMARY KEY (user_id, game_id, season_id)
);
```

At season end: snapshot all ratings, reset phi to a higher value (partial reset).

---

## Module Structure

```
backend/src/replay/
├── __init__.py
├── event_store.py       # EventStore — append/query game events
├── state_builder.py     # Reconstruct state from events
├── routes.py            # Replay REST endpoints
└── snapshots.py         # Periodic snapshot management

backend/src/ranking/
├── __init__.py
├── glicko2.py           # Glicko-2 algorithm implementation
├── service.py           # RankingService — update/query ratings
├── routes.py            # Leaderboard REST endpoints
└── tasks.py             # Async tasks (post-game update, decay cron)
```
