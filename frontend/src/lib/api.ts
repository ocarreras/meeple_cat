import type { AuthTokenResponse, CreateMatchResponse } from './types';

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
