import type { GameEvent, CommandWindowEntry, PlayerView } from './types';

const PLAYER_COLORS = ['#ef4444', '#3b82f6', '#22c55e', '#eab308', '#a855f7'];

let entryCounter = 0;

function getPlayerInfo(
  playerId: string | null,
  view: PlayerView | null,
): { name: string; color: string } {
  if (!playerId || !view) return { name: 'Unknown', color: '#888' };
  const player = view.players.find((p) => p.player_id === playerId);
  if (!player) return { name: playerId.slice(0, 8), color: '#888' };
  return {
    name: player.display_name,
    color: PLAYER_COLORS[player.seat_index % PLAYER_COLORS.length],
  };
}

export function formatGameEvent(
  event: GameEvent,
  view: PlayerView | null,
): CommandWindowEntry | null {
  if (view?.game_id === 'carcassonne') {
    return formatCarcassonneEvent(event, view);
  }
  return formatGenericEvent(event, view);
}

function formatCarcassonneEvent(
  event: GameEvent,
  view: PlayerView | null,
): CommandWindowEntry | null {
  const { name, color } = getPlayerInfo(event.player_id, view);

  switch (event.event_type) {
    case 'feature_scored': {
      const featureType = event.payload.feature_type as string;
      const points = event.payload.points as number;
      const tiles = event.payload.tiles as string[];
      return {
        id: `evt-${++entryCounter}`,
        timestamp: Date.now(),
        type: 'event',
        text: `${name} scored ${points} points on ${featureType}`,
        playerColor: color,
        tiles,
        featureType,
      };
    }
    case 'end_game_points': {
      const points = event.payload.points as number;
      const breakdown = event.payload.breakdown as Record<string, number>;
      const parts = Object.entries(breakdown)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => `${k}: ${v}`)
        .join(', ');
      return {
        id: `evt-${++entryCounter}`,
        timestamp: Date.now(),
        type: 'event',
        text: `${name} scored ${points} end-game points${parts ? ` (${parts})` : ''}`,
        playerColor: color,
      };
    }
    default:
      return null;
  }
}

function formatGenericEvent(
  event: GameEvent,
  view: PlayerView | null,
): CommandWindowEntry | null {
  const { name, color } = getPlayerInfo(event.player_id, view);
  return {
    id: `evt-${++entryCounter}`,
    timestamp: Date.now(),
    type: 'event',
    text: `${name}: ${event.event_type}`,
    playerColor: color,
  };
}
