# 03 — Frontend Architecture

Next.js (App Router) with TypeScript. Desktop-first, mobile-friendly.
State management via Zustand for client state and React Query for server state.

---

## 1. Page Routes

```
/                           # Landing page — game catalog, featured matches
/login                      # Auth provider selection
/auth/callback              # Handles redirect from OIDC providers
/lobby                      # Browse and create game rooms
/game/[matchId]             # Active game (WebSocket connection)
/replay/[matchId]           # Replay viewer
/profile/[userId]           # User profile, stats, match history
/profile/me                 # Own profile (edit mode)
/leaderboard/[gameId]       # Game-specific leaderboard
/bots                       # Manage your bots (authenticated)
/bots/[botId]               # Bot details, stats
```

### 1.1 Layout Hierarchy

```
RootLayout (app/layout.tsx)
├── NavBar                     # Top navigation (always visible)
│   ├── Logo + Home link
│   ├── Game catalog dropdown
│   ├── Lobby link
│   └── User avatar + dropdown (login if anonymous)
├── children                   # Page content
└── Footer (minimal)

GameLayout (app/game/[matchId]/layout.tsx)
├── No NavBar (full screen for game)
├── GameHeader (minimal: timer, scores, exit button)
└── children (game renderer)
```

### 1.2 Server vs Client Components

| Component | Type | Rationale |
|---|---|---|
| Landing page | Server | Static content, SEO |
| Game catalog | Server | Fetched at request time, cacheable |
| Leaderboard | Server | Fetched at request time, cacheable |
| User profile | Server | Static-ish, SEO for public profiles |
| Lobby room list | Client | Real-time updates (polling or WS) |
| Game renderer | Client | WebSocket, interactive, Canvas |
| Replay viewer | Client | Interactive playback controls |
| Auth callback | Client | Processes URL params, stores tokens |

---

## 2. State Management

### 2.1 Server State (React Query / TanStack Query)

For all REST API data — user profiles, game catalog, leaderboards, match
history, lobby rooms, bot management.

```typescript
// Example: fetch game catalog
const { data: games } = useQuery({
  queryKey: ['games'],
  queryFn: () => api.get('/games'),
  staleTime: 5 * 60 * 1000,  // Cache for 5 min
});

// Example: lobby rooms (poll every 5s)
const { data: rooms } = useQuery({
  queryKey: ['rooms'],
  queryFn: () => api.get('/rooms'),
  refetchInterval: 5000,
});
```

### 2.2 Client State (Zustand)

For WebSocket-driven game state, UI state, and user preferences.

```typescript
interface GameStore {
  // Connection
  matchId: string | null;
  connected: boolean;
  lastSeq: number;

  // Game state (received from server)
  view: PlayerView | null;
  phase: string | null;
  validActions: ActionPayload[];
  timerState: Record<string, number>;

  // UI state
  selectedAction: ActionPayload | null;
  boardZoom: number;
  boardOffset: { x: number; y: number };

  // Actions
  setView: (view: PlayerView) => void;
  setValidActions: (actions: ActionPayload[]) => void;
  selectAction: (action: ActionPayload | null) => void;
  updateTimer: (timers: Record<string, number>) => void;
  reset: () => void;
}

const useGameStore = create<GameStore>((set) => ({
  matchId: null,
  connected: false,
  lastSeq: 0,
  view: null,
  phase: null,
  validActions: [],
  timerState: {},
  selectedAction: null,
  boardZoom: 1,
  boardOffset: { x: 0, y: 0 },

  setView: (view) => set({
    view,
    phase: view.current_phase.name,
    lastSeq: view.seq ?? 0,
  }),
  setValidActions: (actions) => set({ validActions: actions }),
  selectAction: (action) => set({ selectedAction: action }),
  updateTimer: (timers) => set({ timerState: timers }),
  reset: () => set({
    matchId: null, connected: false, view: null,
    phase: null, validActions: [], selectedAction: null,
  }),
}));
```

### 2.3 No Optimistic Updates

Since the server is authoritative, the client does **not** apply actions
optimistically. The flow is:

```
1. User clicks → UI shows "submitting" state (button disabled)
2. Client sends action via WebSocket
3. Server validates, applies, broadcasts new state
4. Client receives state_update → UI updates
```

This adds ~50-100ms of perceived latency (round trip) which is acceptable
for board games. The simplicity benefit is large: no rollback logic, no
state divergence bugs.

---

## 3. WebSocket Client

### 3.1 useWebSocket Hook

```typescript
interface UseWebSocketOptions {
  matchId: string;
  onMessage: (message: WSMessage) => void;
  onConnect: () => void;
  onDisconnect: () => void;
}

function useWebSocket({ matchId, onMessage, onConnect, onDisconnect }: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const lastSeqRef = useRef(0);
  const reconnectAttemptRef = useRef(0);

  const connect = useCallback(async () => {
    // Get a WS ticket from the REST API
    const { ticket } = await api.post('/auth/ws-ticket');

    const url = `${WS_BASE_URL}/ws/game/${matchId}?ticket=${ticket}&last_seq=${lastSeqRef.current}`;
    const ws = new WebSocket(url);

    ws.onopen = () => {
      reconnectAttemptRef.current = 0;
      onConnect();
    };

    ws.onmessage = (event) => {
      const message: WSMessage = JSON.parse(event.data);
      if (message.seq) {
        lastSeqRef.current = message.seq;
      }
      onMessage(message);
    };

    ws.onclose = (event) => {
      onDisconnect();
      if (event.code !== 1000) {
        // Unexpected close — reconnect with backoff
        scheduleReconnect();
      }
    };

    wsRef.current = ws;
  }, [matchId]);

  const scheduleReconnect = useCallback(() => {
    const attempt = reconnectAttemptRef.current++;
    const delay = Math.min(1000 * Math.pow(2, attempt), 30000); // Max 30s
    setTimeout(connect, delay);
  }, [connect]);

  const sendAction = useCallback((actionType: string, payload: any) => {
    wsRef.current?.send(JSON.stringify({
      type: 'action',
      payload: { action_type: actionType, data: payload },
    }));
  }, []);

  const sendMessage = useCallback((type: string, payload?: any) => {
    wsRef.current?.send(JSON.stringify({ type, payload }));
  }, []);

  useEffect(() => {
    connect();
    return () => wsRef.current?.close(1000);
  }, [connect]);

  return { sendAction, sendMessage };
}
```

### 3.2 Message Handler (integrates with Zustand)

```typescript
function useGameConnection(matchId: string) {
  const store = useGameStore();

  const handleMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
      case 'connected':
        store.setView(msg.payload.view);
        break;
      case 'state_update':
        store.setView(msg.payload.view);
        break;
      case 'action_required':
        store.setValidActions(msg.payload.valid_actions);
        break;
      case 'timer_update':
        store.updateTimer(msg.payload.player_timers);
        break;
      case 'game_over':
        store.setGameOver(msg.payload.result);
        break;
      case 'error':
        store.setError(msg.payload);
        break;
      // ... other message types
    }
  }, [store]);

  const { sendAction, sendMessage } = useWebSocket({
    matchId,
    onMessage: handleMessage,
    onConnect: () => store.setConnected(true),
    onDisconnect: () => store.setConnected(false),
  });

  return { sendAction, sendMessage };
}
```

---

## 4. Game Rendering Architecture

### 4.1 Reusable Primitives

Located in `frontend/src/components/ui/game/`:

```typescript
// Grid — renders a 2D grid with zoom/pan
interface GridProps {
  cellSize: number;
  cells: Map<string, React.ReactNode>;   // "x,y" → renderer
  highlights?: Map<string, string>;       // "x,y" → highlight color
  onCellClick?: (x: number, y: number) => void;
  onCellHover?: (x: number, y: number) => void;
  zoom: number;
  offset: { x: number; y: number };
  onZoomChange: (zoom: number) => void;
  onOffsetChange: (offset: { x: number; y: number }) => void;
}

// ScoreBoard — displays player scores and active player indicator
interface ScoreBoardProps {
  players: PlayerInfo[];
  scores: Record<string, number>;
  activePlayerId?: string;
  currentUserId?: string;
}

// Timer — countdown display with warning colors
interface TimerProps {
  playerId: string;
  remainingMs: number;
  isActive: boolean;                       // Ticking or paused
  warningThresholdMs?: number;             // Turn yellow/red
}

// Hand — displays a hand of cards/tiles (horizontal row)
interface HandProps<T> {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  selectedIndex?: number;
  onSelect?: (index: number) => void;
}

// TokenStack — displays a stack of tokens/meeples with count
interface TokenStackProps {
  color: string;
  count: number;
  maxDisplay?: number;
  icon: React.ReactNode;
}

// Dice — animated dice roll display
interface DiceProps {
  values: number[];
  rolling?: boolean;
  onRollComplete?: () => void;
}

// ConfirmationDialog — "Are you sure?" for destructive actions
// ChatPanel — in-game chat sidebar
// ConnectionStatus — WebSocket connection indicator
```

### 4.2 Game Component Interface

Each game provides a root component that receives standardized props:

```typescript
interface GameRendererProps {
  view: PlayerView;             // Current game state (filtered)
  validActions: ActionPayload[];
  onAction: (actionType: string, payload: any) => void;
  myPlayerId: string | null;    // Null for spectators
  isMyTurn: boolean;
  phase: string;
}

// Game plugins register their renderer:
const GAME_RENDERERS: Record<string, React.ComponentType<GameRendererProps>> = {
  carcassonne: CarcassonneRenderer,
  // future: caylus: CaylusRenderer, etc.
};
```

### 4.3 Game Page Composition

```typescript
// app/game/[matchId]/page.tsx
export default function GamePage({ params }: { params: { matchId: string } }) {
  const { matchId } = params;
  const store = useGameStore();
  const { sendAction } = useGameConnection(matchId);

  if (!store.view) return <LoadingSpinner />;

  const GameRenderer = GAME_RENDERERS[store.view.game_id];
  if (!GameRenderer) return <div>Unknown game: {store.view.game_id}</div>;

  const myPlayerId = store.view.viewer_id;
  const isMyTurn = store.validActions.length > 0;

  return (
    <div className="game-container">
      <GameHeader
        players={store.view.players}
        scores={store.view.scores}
        timers={store.timerState}
        phase={store.phase}
      />
      <GameRenderer
        view={store.view}
        validActions={store.validActions}
        onAction={sendAction}
        myPlayerId={myPlayerId}
        isMyTurn={isMyTurn}
        phase={store.phase!}
      />
    </div>
  );
}
```

### 4.4 Carcassonne Renderer (Game-Specific)

```typescript
// components/games/carcassonne/CarcassonneRenderer.tsx

function CarcassonneRenderer({
  view, validActions, onAction, myPlayerId, isMyTurn, phase
}: GameRendererProps) {
  const gameData = view.game_data as CarcassonneView;

  return (
    <div className="carcassonne">
      <div className="board-area">
        <CarcassonneBoard
          tiles={gameData.board.tiles}
          features={gameData.features}
          validPlacements={phase === 'place_tile' ? validActions : []}
          onTilePlaced={(x, y, rotation) =>
            onAction('place_tile', { x, y, rotation })
          }
          lastPlacedPosition={gameData.last_placed_position}
          meeplePlacements={phase === 'place_meeple' ? validActions : []}
          onMeeplePlaced={(spot) =>
            onAction('place_meeple', { meeple_spot: spot })
          }
          onMeepleSkipped={() =>
            onAction('place_meeple', { skip: true })
          }
        />
      </div>
      <div className="sidebar">
        <TilePreview
          tile={gameData.current_tile}
          onRotate={(rotation) => { /* Update rotation state */ }}
        />
        <MeepleSupply
          supply={gameData.meeple_supply}
          players={view.players}
        />
        <ScoreBoard
          players={view.players}
          scores={view.scores}
          activePlayerId={myPlayerId}
        />
        <div className="tiles-remaining">
          {gameData.tiles_remaining} tiles remaining
        </div>
      </div>
    </div>
  );
}
```

### 4.5 Board Rendering: Canvas vs DOM

**Decision: Canvas** (via HTML5 Canvas API, no heavy library).

Rationale:
- Board can have 72+ tiles — DOM nodes would be expensive
- Zoom/pan is natural with Canvas transforms
- Tile images render faster as Canvas drawImage
- Meeple overlays are simple colored circles/shapes

The Canvas is wrapped in a React component that handles:
- Mouse/touch events for interaction (click, drag, pinch zoom)
- Render loop triggered by state changes (not animation frame)
- Hit testing for tile/meeple click detection

```typescript
function CarcassonneBoard({ tiles, validPlacements, onTilePlaced, ... }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [camera, setCamera] = useState({ x: 0, y: 0, zoom: 1 });

  useEffect(() => {
    const ctx = canvasRef.current?.getContext('2d');
    if (!ctx) return;
    renderBoard(ctx, tiles, camera, validPlacements, ...);
  }, [tiles, camera, validPlacements]);

  return (
    <canvas
      ref={canvasRef}
      onMouseDown={handlePanStart}
      onMouseMove={handlePanMove}
      onMouseUp={handlePanEnd}
      onWheel={handleZoom}
      onClick={handleClick}
    />
  );
}
```

---

## 5. Replay Viewer

### 5.1 Architecture

The replay viewer loads the full event log via REST and reconstructs state
client-side:

```typescript
function ReplayPage({ params }: { params: { matchId: string } }) {
  const { data: replay } = useQuery({
    queryKey: ['replay', params.matchId],
    queryFn: () => api.get(`/matches/${params.matchId}/replay`),
  });

  const [currentEvent, setCurrentEvent] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  // Reconstruct state at current event
  const currentState = useMemo(() => {
    if (!replay) return null;
    return reconstructStateAt(replay.initial_state, replay.events, currentEvent);
  }, [replay, currentEvent]);

  return (
    <div className="replay-viewer">
      <GameRenderer
        view={stateToView(currentState)}
        validActions={[]}
        onAction={() => {}}
        myPlayerId={null}
        isMyTurn={false}
        phase={currentState?.phase ?? ''}
      />
      <ReplayControls
        totalEvents={replay?.events.length ?? 0}
        currentEvent={currentEvent}
        isPlaying={isPlaying}
        onSeek={setCurrentEvent}
        onPlayPause={() => setIsPlaying(!isPlaying)}
        onStepForward={() => setCurrentEvent(e => Math.min(e + 1, replay!.events.length))}
        onStepBackward={() => setCurrentEvent(e => Math.max(e - 1, 0))}
      />
      <EventLog
        events={replay?.events ?? []}
        currentEvent={currentEvent}
        onEventClick={setCurrentEvent}
      />
    </div>
  );
}
```

### 5.2 State Reconstruction

The replay needs game-specific logic to reconstruct state from events.
Options:
1. **Duplicate game logic in TypeScript** — accurate but maintenance burden
2. **Call server to reconstruct** — simple but adds latency for seeking
3. **Use server-generated state snapshots** — fast seeking, no client logic

For V1: **option 2** with caching. Client requests state at a specific event
number from the server. Responses are cached locally.

```typescript
async function getStateAtEvent(matchId: string, eventNumber: number): Promise<GameState> {
  return api.get(`/matches/${matchId}/state-at/${eventNumber}`);
}
```

The server reconstructs using its Python game engine (which is the source
of truth). This avoids duplicating game logic across languages.

---

## 6. Responsive Design

### 6.1 Breakpoints

```css
/* Desktop-first breakpoints */
@media (max-width: 1200px) { /* Large tablets, small desktops */ }
@media (max-width: 768px)  { /* Tablets */ }
@media (max-width: 480px)  { /* Mobile */ }
```

### 6.2 Game Layout Adaptation

```
Desktop (>1200px):
┌──────────────────────────────────────────┐
│ Header (scores, timer)                   │
├─────────────────────┬────────────────────┤
│                     │ Sidebar            │
│   Board (canvas)    │ - Tile preview     │
│                     │ - Meeple supply    │
│                     │ - Score details    │
│                     │ - Chat             │
└─────────────────────┴────────────────────┘

Tablet (768-1200px):
┌──────────────────────────────────────────┐
│ Header (scores, timer, compact)          │
├──────────────────────────────────────────┤
│                                          │
│   Board (canvas, full width)             │
│                                          │
├──────────────────────────────────────────┤
│ Bottom bar: tile preview | meeples       │
└──────────────────────────────────────────┘

Mobile (<768px):
┌──────────────────────┐
│ Mini header          │
├──────────────────────┤
│                      │
│  Board (canvas,      │
│  pinch zoom)         │
│                      │
├──────────────────────┤
│ Action bar (tile +   │
│ confirm button)      │
└──────────────────────┘
```

---

## 7. Performance

### 7.1 Code Splitting

Each game's renderer is lazy-loaded:

```typescript
const GAME_RENDERERS: Record<string, React.LazyExoticComponent<...>> = {
  carcassonne: lazy(() => import('@/components/games/carcassonne/CarcassonneRenderer')),
};
```

This ensures the lobby page doesn't load any game-specific code.

### 7.2 Asset Loading

Tile images per game are loaded on demand when the game starts:

```typescript
async function preloadTileImages(gameId: string): Promise<Map<string, HTMLImageElement>> {
  const manifest = await import(`@/assets/games/${gameId}/manifest.json`);
  const images = new Map();
  await Promise.all(
    manifest.tiles.map(async (tile: string) => {
      const img = new Image();
      img.src = `/assets/games/${gameId}/tiles/${tile}.png`;
      await img.decode();
      images.set(tile, img);
    })
  );
  return images;
}
```

---

## 8. Module Structure

```
frontend/src/
├── app/
│   ├── layout.tsx                 # Root layout
│   ├── page.tsx                   # Landing page
│   ├── login/page.tsx
│   ├── auth/callback/page.tsx
│   ├── lobby/page.tsx
│   ├── game/[matchId]/
│   │   ├── layout.tsx             # Game layout (no nav)
│   │   └── page.tsx               # Game page (WS connection)
│   ├── replay/[matchId]/page.tsx
│   ├── profile/[userId]/page.tsx
│   ├── leaderboard/[gameId]/page.tsx
│   └── bots/
│       ├── page.tsx               # Bot management
│       └── [botId]/page.tsx
├── components/
│   ├── ui/                        # Shadcn-style generic UI (button, card, etc.)
│   ├── game/                      # Reusable game primitives
│   │   ├── Grid.tsx
│   │   ├── ScoreBoard.tsx
│   │   ├── Timer.tsx
│   │   ├── Hand.tsx
│   │   ├── TokenStack.tsx
│   │   ├── ChatPanel.tsx
│   │   ├── ConnectionStatus.tsx
│   │   └── ReplayControls.tsx
│   ├── games/                     # Game-specific renderers
│   │   └── carcassonne/
│   │       ├── CarcassonneRenderer.tsx
│   │       ├── CarcassonneBoard.tsx
│   │       ├── TilePreview.tsx
│   │       ├── MeepleSupply.tsx
│   │       └── MeeplePlacement.tsx
│   └── layout/
│       ├── NavBar.tsx
│       ├── GameHeader.tsx
│       └── Footer.tsx
├── hooks/
│   ├── useWebSocket.ts
│   ├── useGameConnection.ts
│   ├── useAuth.ts
│   └── useTimer.ts
├── stores/
│   ├── gameStore.ts               # Zustand game state
│   └── authStore.ts               # Auth state (user, tokens)
├── lib/
│   ├── api.ts                     # REST API client (fetch wrapper)
│   ├── types.ts                   # Shared TypeScript types
│   └── utils.ts
└── assets/
    └── games/
        └── carcassonne/
            ├── manifest.json
            └── tiles/             # Tile images
```
