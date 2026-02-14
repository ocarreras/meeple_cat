import type {
  AuthTokenResponse,
  CreateMatchResponse,
  Room,
  JoinRoomResponse,
  StartRoomResponse,
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

async function fetchJson<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    let errorData;
    try {
      errorData = await response.json();
    } catch {
      errorData = { message: response.statusText };
    }
    throw new ApiError(
      errorData.message || `HTTP ${response.status}: ${response.statusText}`,
      response.status,
      errorData
    );
  }

  return response.json();
}

/**
 * Get authentication token for a display name
 * POST /api/v1/auth/token
 */
export async function getToken(displayName: string): Promise<AuthTokenResponse> {
  return fetchJson<AuthTokenResponse>(`${API_BASE_URL}/auth/token`, {
    method: 'POST',
    body: JSON.stringify({ display_name: displayName }),
  });
}

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
    config?: Record<string, unknown>;
  },
): Promise<CreateMatchResponse> {
  const body: {
    game_id: string;
    player_display_names: string[];
    random_seed?: number;
    bot_seats?: number[];
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
  if (options?.config && Object.keys(options.config).length > 0) {
    body.config = options.config;
  }

  return fetchJson<CreateMatchResponse>(`${API_BASE_URL}/matches`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
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
  token: string,
  gameId: string,
  maxPlayers: number,
  config: Record<string, unknown> = {},
): Promise<Room> {
  return fetchJson<Room>(`${API_BASE_URL}/rooms`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ game_id: gameId, max_players: maxPlayers, config }),
  });
}

export async function joinRoom(
  token: string,
  roomId: string,
): Promise<JoinRoomResponse> {
  return fetchJson<JoinRoomResponse>(`${API_BASE_URL}/rooms/${roomId}/join`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function leaveRoom(
  token: string,
  roomId: string,
): Promise<{ ok: boolean }> {
  return fetchJson<{ ok: boolean }>(`${API_BASE_URL}/rooms/${roomId}/leave`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function toggleReady(
  token: string,
  roomId: string,
): Promise<Room> {
  return fetchJson<Room>(`${API_BASE_URL}/rooms/${roomId}/ready`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function addBot(
  token: string,
  roomId: string,
  botId: string = 'random',
): Promise<Room> {
  return fetchJson<Room>(`${API_BASE_URL}/rooms/${roomId}/add-bot`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ bot_id: botId }),
  });
}

export async function startRoom(
  token: string,
  roomId: string,
): Promise<StartRoomResponse> {
  return fetchJson<StartRoomResponse>(
    `${API_BASE_URL}/rooms/${roomId}/start`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    },
  );
}

/**
 * Generate WebSocket URL for a match
 * The URL goes through Next.js proxy which forwards to the backend
 */
export function getWsUrl(matchId: string, token: string): string {
  // Determine protocol based on window.location (ws:// for http://, wss:// for https://)
  // But for the proxy, we need to use the current host
  // In development, this will be localhost:3000
  // The proxy rewrites /ws/* to backend at localhost:8000

  // Note: This function assumes it's called in a browser context
  if (typeof window === 'undefined') {
    // Server-side rendering fallback
    return `ws://localhost:3000/ws/game/${matchId}?token=${token}`;
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;

  return `${protocol}//${host}/ws/game/${matchId}?token=${token}`;
}
