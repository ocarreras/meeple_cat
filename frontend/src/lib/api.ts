import type {
  AuthTokenResponse,
  CreateMatchResponse,
  Room,
  JoinRoomResponse,
  StartRoomResponse,
  UserInfoResponse,
  AuthProvider,
  MatchHistoryEntry,
} from './types';

const API_BASE_URL = '/api/v1';

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public response?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

// ---------------------------------------------------------------------------
// Token refresh interceptor (mutex to prevent parallel refresh requests)
// ---------------------------------------------------------------------------

let refreshPromise: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });
      return resp.ok;
    } catch {
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

// ---------------------------------------------------------------------------
// Core fetch helper
// ---------------------------------------------------------------------------

function authHeaders(token?: string): Record<string, string> {
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

async function fetchJson<T>(
  url: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const response = await fetch(url, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(token),
      ...options.headers,
    },
  });

  // If 401, try refreshing the access token (for cookie-based auth)
  if (response.status === 401 && !token) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      return fetchJson<T>(url, options, token);
    }
  }

  if (!response.ok) {
    let errorData;
    try {
      errorData = await response.json();
    } catch {
      errorData = { message: response.statusText };
    }
    throw new ApiError(
      errorData.detail || errorData.message || `HTTP ${response.status}: ${response.statusText}`,
      response.status,
      errorData
    );
  }

  return response.json();
}

// ---------------------------------------------------------------------------
// Auth API
// ---------------------------------------------------------------------------

/**
 * Get authentication token for a guest display name
 * POST /api/v1/auth/token
 */
export async function getToken(displayName: string): Promise<AuthTokenResponse> {
  return fetchJson<AuthTokenResponse>(`${API_BASE_URL}/auth/token`, {
    method: 'POST',
    body: JSON.stringify({ display_name: displayName }),
  });
}

/**
 * List available OIDC providers
 * GET /api/v1/auth/providers
 */
export async function getProviders(): Promise<AuthProvider[]> {
  return fetchJson<AuthProvider[]>(`${API_BASE_URL}/auth/providers`);
}

/**
 * Get current user info (works with both cookie and Bearer auth)
 * GET /api/v1/auth/me
 */
export async function getMe(token?: string): Promise<UserInfoResponse> {
  return fetchJson<UserInfoResponse>(`${API_BASE_URL}/auth/me`, {}, token);
}

/**
 * Logout (clear cookies, revoke refresh token)
 * POST /api/v1/auth/logout
 */
export async function logout(): Promise<void> {
  await fetch(`${API_BASE_URL}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  });
}

/**
 * Get a single-use WebSocket connection ticket
 * POST /api/v1/auth/ws-ticket
 */
export async function getWsTicket(token?: string): Promise<string> {
  const resp = await fetchJson<{ ticket: string }>(
    `${API_BASE_URL}/auth/ws-ticket`,
    { method: 'POST' },
    token,
  );
  return resp.ticket;
}

// ---------------------------------------------------------------------------
// Games API
// ---------------------------------------------------------------------------

export interface GameInfo {
  game_id: string;
  display_name: string;
  min_players: number;
  max_players: number;
  description: string;
}

export async function getGames(): Promise<GameInfo[]> {
  return fetchJson<GameInfo[]>(`${API_BASE_URL}/games`);
}

// ---------------------------------------------------------------------------
// Match API
// ---------------------------------------------------------------------------

/**
 * Create a new match
 * POST /api/v1/matches
 */
export async function createMatch(
  token: string,
  gameId: string,
  playerNames: string[],
  options?: {
    randomSeed?: number;
    botSeats?: number[];
    botId?: string;
    config?: Record<string, unknown>;
  },
): Promise<CreateMatchResponse> {
  const body: {
    game_id: string;
    player_display_names: string[];
    random_seed?: number;
    bot_seats?: number[];
    bot_id?: string;
    config?: Record<string, unknown>;
  } = {
    game_id: gameId,
    player_display_names: playerNames,
  };

  if (options?.randomSeed !== undefined) {
    body.random_seed = options.randomSeed;
  }
  if (options?.botSeats && options.botSeats.length > 0) {
    body.bot_seats = options.botSeats;
  }
  if (options?.botId) {
    body.bot_id = options.botId;
  }
  if (options?.config && Object.keys(options.config).length > 0) {
    body.config = options.config;
  }

  return fetchJson<CreateMatchResponse>(
    `${API_BASE_URL}/matches`,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
    token,
  );
}

// ---------------------------------------------------------------------------
// Room API
// ---------------------------------------------------------------------------

export async function listRooms(gameId?: string): Promise<Room[]> {
  const params = gameId ? `?game_id=${encodeURIComponent(gameId)}` : '';
  return fetchJson<Room[]>(`${API_BASE_URL}/rooms${params}`);
}

export async function getRoom(roomId: string): Promise<Room> {
  return fetchJson<Room>(`${API_BASE_URL}/rooms/${roomId}`);
}

export async function createRoom(
  gameId: string,
  maxPlayers: number,
  config: Record<string, unknown> = {},
  token?: string,
): Promise<Room> {
  return fetchJson<Room>(
    `${API_BASE_URL}/rooms`,
    {
      method: 'POST',
      body: JSON.stringify({ game_id: gameId, max_players: maxPlayers, config }),
    },
    token,
  );
}

export async function joinRoom(
  roomId: string,
  token?: string,
): Promise<JoinRoomResponse> {
  return fetchJson<JoinRoomResponse>(
    `${API_BASE_URL}/rooms/${roomId}/join`,
    { method: 'POST' },
    token,
  );
}

export async function leaveRoom(
  roomId: string,
  token?: string,
): Promise<{ ok: boolean }> {
  return fetchJson<{ ok: boolean }>(
    `${API_BASE_URL}/rooms/${roomId}/leave`,
    { method: 'POST' },
    token,
  );
}

export async function toggleReady(
  roomId: string,
  token?: string,
): Promise<Room> {
  return fetchJson<Room>(
    `${API_BASE_URL}/rooms/${roomId}/ready`,
    { method: 'POST' },
    token,
  );
}

export async function addBot(
  roomId: string,
  botId: string = 'random',
  token?: string,
): Promise<Room> {
  return fetchJson<Room>(
    `${API_BASE_URL}/rooms/${roomId}/add-bot`,
    {
      method: 'POST',
      body: JSON.stringify({ bot_id: botId }),
    },
    token,
  );
}

export async function startRoom(
  roomId: string,
  token?: string,
): Promise<StartRoomResponse> {
  return fetchJson<StartRoomResponse>(
    `${API_BASE_URL}/rooms/${roomId}/start`,
    { method: 'POST' },
    token,
  );
}

// ---------------------------------------------------------------------------
// User / Profile API
// ---------------------------------------------------------------------------

export async function getMatchHistory(
  userId: string,
  limit: number = 20,
  offset: number = 0,
): Promise<MatchHistoryEntry[]> {
  return fetchJson<MatchHistoryEntry[]>(
    `${API_BASE_URL}/users/${userId}/matches?limit=${limit}&offset=${offset}`,
  );
}

// ---------------------------------------------------------------------------
// WebSocket URL helper
// ---------------------------------------------------------------------------

/**
 * Generate WebSocket URL for a match using ticket-based auth.
 * Falls back to token-based auth if ticket is not available.
 */
export function getWsUrl(matchId: string, authParam: string): string {
  if (typeof window === 'undefined') {
    return `ws://localhost:3000/ws/game/${matchId}?${authParam}`;
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;

  return `${protocol}//${host}/ws/game/${matchId}?${authParam}`;
}
