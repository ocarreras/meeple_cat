// Core type aliases
export type MatchId = string;
export type GameId = string;
export type PlayerId = string;

// Game status enum
export type GameStatus = "waiting" | "active" | "paused" | "finished" | "abandoned";

// Concurrent mode for phases
export type ConcurrentMode = "sequential" | "simultaneous" | "none";

// Player model
export interface Player {
  player_id: PlayerId;
  display_name: string;
  seat_index: number;
  is_bot: boolean;
  bot_id: string | null;
}

// Expected action for phases
export interface ExpectedAction {
  player_id: PlayerId | null;
  action_type: string;
  constraints: Record<string, unknown>;
  timeout_ms: number | null;
}

// Phase model
export interface Phase {
  name: string;
  concurrent_mode: ConcurrentMode;
  expected_actions: ExpectedAction[];
  auto_resolve: boolean;
  metadata: Record<string, unknown>;
}

// Carcassonne-specific types

// Board tile structure
export interface BoardTile {
  tile_type_id: string;
  rotation: number;
}

// Board structure
export interface Board {
  tiles: Record<string, BoardTile>; // keyed by "x,y" position string
  open_positions: string[]; // array of "x,y" position strings
}

// Meeple placement on feature
export interface MeeplePlacement {
  player_id: PlayerId;
  position: string; // "x,y" position
  spot: string; // e.g., "city_N", "road_N", etc.
}

// Feature structure
export interface Feature {
  feature_type: string; // "city", "road", "monastery", "field"
  tiles: string[]; // array of "x,y" position strings
  meeples: MeeplePlacement[];
  is_complete: boolean;
  [key: string]: unknown; // allow additional properties
}

// Carcassonne game data structure
// Maps position "x,y" -> { spot_name: feature_id }
export type TileFeatureMap = Record<string, Record<string, string>>;

export interface CarcassonneGameData {
  board: Board;
  features: Record<string, Feature>; // keyed by feature ID
  tile_feature_map: TileFeatureMap; // position -> spot -> feature_id
  current_tile: string | null; // tile type ID like "A", "B", etc.
  tiles_remaining: number;
  meeple_supply: Record<PlayerId, number>; // player_id -> count
  scores: Record<PlayerId, number>; // player_id -> score
  last_placed_position: string | null; // "x,y" position or null
  end_game_breakdown?: Record<PlayerId, Record<string, number>>; // per-player per-category end-game points
}

// Ein Stein Dojo types

export interface EinsteinDojoBoard {
  kite_owners: Record<string, string>;  // "q,r:k" -> player_id
  hex_states: Record<string, string>;   // "q,r" -> HexState
  placed_pieces: {
    player_id: string;
    orientation: number;
    anchor_q: number;
    anchor_r: number;
  }[];
}

export interface EinsteinDojoGameData {
  board: EinsteinDojoBoard;
  tiles_remaining: Record<PlayerId, number>;
  scores: Record<PlayerId, number>;
  current_player_index: number;
}

// Ein Stein Dojo action types
export type EinsteinPlaceTileAction = {
  anchor_q: number;
  anchor_r: number;
  orientation: number;
};

// Union of all game data types
export type GameData = CarcassonneGameData | EinsteinDojoGameData;

// Main PlayerView model
export interface PlayerView {
  match_id: MatchId;
  game_id: GameId;
  players: Player[];
  current_phase: Phase;
  status: GameStatus;
  turn_number: number;
  scores: Record<string, number>;
  player_timers: Record<string, number>;
  game_data: GameData;
  valid_actions: ValidAction[];
  viewer_id: PlayerId | null;
  is_spectator: boolean;
  forfeited_players: string[];
  disconnected_players: string[];
}

// Valid action types for Carcassonne
export type TilePlacementAction = {
  x: number;
  y: number;
  rotation: number;
  meeple_spots?: string[];
};

export type MeeplePlacementAction = {
  meeple_spot: string;
};

export type SkipAction = {
  skip: true;
};

export type ValidAction = TilePlacementAction | MeeplePlacementAction | SkipAction;

// WebSocket message types

// Server to Client messages
export type ServerMessageType =
  | "connected"
  | "state_update"
  | "error"
  | "pong"
  | "game_over"
  | "action_committed"
  | "player_disconnected"
  | "player_reconnected"
  | "player_forfeited";

export interface ConnectedPayload {
  match_id: MatchId;
  player_id: PlayerId;
}

export interface StateUpdatePayload {
  view: PlayerView;
}

export interface ErrorPayload {
  error: string;
  message: string;
}

export interface GameOverPayload {
  winners: PlayerId[];
  final_scores: Record<PlayerId, number>;
  reason: string;
}

export interface PlayerDisconnectedPayload {
  player_id: PlayerId;
  grace_period_seconds: number;
}

export interface PlayerReconnectedPayload {
  player_id: PlayerId;
}

export interface PlayerForfeitedPayload {
  player_id: PlayerId;
}

export interface ServerMessage {
  type: ServerMessageType;
  payload: ConnectedPayload | StateUpdatePayload | ErrorPayload | GameOverPayload | PlayerDisconnectedPayload | PlayerReconnectedPayload | PlayerForfeitedPayload | Record<string, unknown>;
}

// Client to Server messages
export type ClientMessageType = "action" | "ping" | "resign";

export interface PlaceTilePayload {
  x: number;
  y: number;
  rotation: number;
}

export interface PlaceMeeplePayload {
  meeple_spot: string;
}

export interface SkipMeeplePayload {
  skip: true;
}

export type ActionPayload = PlaceTilePayload | PlaceMeeplePayload | SkipMeeplePayload | EinsteinPlaceTileAction;

export interface ActionMessage {
  action_type: string;
  payload: ActionPayload;
}

export interface ClientMessage {
  type: ClientMessageType;
  payload?: ActionMessage | Record<string, unknown>;
}

// Auth types
export interface AuthProvider {
  provider_id: string;
  display_name: string;
}

export interface UserInfoResponse {
  user_id: string;
  display_name: string;
  email: string | null;
  avatar_url: string | null;
  is_guest: boolean;
}

export interface MatchHistoryEntry {
  match_id: string;
  game_id: string;
  status: GameStatus;
  started_at: string | null;
  ended_at: string | null;
  seat_index: number;
  result: string | null;
  score: number | null;
  players: { display_name: string; seat_index: number; score: number | null }[];
}

// API response types
export interface AuthTokenResponse {
  token: string;
  user_id: string;
}

export interface CreateMatchResponse {
  match_id: MatchId;
  game_id: GameId;
  players: Player[];
  status: GameStatus;
}

// Room types

export type RoomStatus = "waiting" | "starting" | "in_game";

export interface RoomSeat {
  seat_index: number;
  user_id: string | null;
  display_name: string | null;
  is_bot: boolean;
  bot_id: string | null;
  is_ready: boolean;
}

export interface Room {
  room_id: string;
  game_id: string;
  created_by: string;
  creator_name: string;
  status: RoomStatus;
  max_players: number;
  config: Record<string, unknown>;
  created_at: string;
  seats: RoomSeat[];
  match_id: string | null;
}

export interface JoinRoomResponse {
  room: Room;
  seat_index: number;
}

export interface StartRoomResponse {
  match_id: string;
  tokens: Record<string, string>;
}

// UI-specific types
export interface TilePlacement {
  x: number;
  y: number;
  rotation: number;
  meeple_spots?: string[];
}

// Type guards
export function isStateUpdatePayload(payload: unknown): payload is StateUpdatePayload {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    'view' in payload
  );
}

export function isErrorPayload(payload: unknown): payload is ErrorPayload {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    'error' in payload &&
    'message' in payload
  );
}

export function isConnectedPayload(payload: unknown): payload is ConnectedPayload {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    'match_id' in payload &&
    'player_id' in payload
  );
}

export function isGameOverPayload(payload: unknown): payload is GameOverPayload {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    'winners' in payload &&
    'final_scores' in payload
  );
}

export function isPlayerDisconnectedPayload(payload: unknown): payload is PlayerDisconnectedPayload {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    'player_id' in payload &&
    'grace_period_seconds' in payload
  );
}

export function isPlayerReconnectedPayload(payload: unknown): payload is PlayerReconnectedPayload {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    'player_id' in payload &&
    !('grace_period_seconds' in payload) &&
    !('winners' in payload)
  );
}

export function isPlayerForfeitedPayload(payload: unknown): payload is PlayerForfeitedPayload {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    'player_id' in payload
  );
}

export function isTilePlacementAction(action: ValidAction): action is TilePlacementAction {
  return 'x' in action && 'y' in action && 'rotation' in action;
}

export function isMeeplePlacementAction(action: ValidAction): action is MeeplePlacementAction {
  return 'meeple_spot' in action;
}

export function isSkipAction(action: ValidAction): action is SkipAction {
  return 'skip' in action;
}
