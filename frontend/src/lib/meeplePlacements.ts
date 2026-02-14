/**
 * Meeple placement pixel positions for each tile type.
 * Ported from carcassonne-react/src/utils/gameLogic.js
 *
 * column/row are pixel offsets from tile center in a 100x100 tile space.
 * type: 1=Monastery, 2=City, 3=Road, 4=Field
 */

import { CarcassonneGameData } from './types';

export interface MeeplePlacementDef {
  column: number;
  row: number;
  type: number;
}

export const MEEPLE_TYPE_MONASTERY = 1;
export const MEEPLE_TYPE_CITY = 2;
export const MEEPLE_TYPE_ROAD = 3;
export const MEEPLE_TYPE_FIELD = 4;

/**
 * Compound edge connections for each meeple spot on each tile type (at rotation 0).
 * Mirrors the backend's TileFeature.edges exactly.
 *
 * Simple edges like "N" connect through a pure field/city/road edge.
 * Compound edges like "S:E" mean "east side of the S road" — used for fields
 * that connect through road-split edges.
 */
const TILE_SPOT_EDGES: Record<string, Record<string, string[]>> = {
  A: { monastery: [], road_S: ['S'], field_NEW: ['N', 'E', 'W', 'S:E', 'S:W'] },
  B: { monastery: [], field_NESW: ['N', 'E', 'S', 'W'] },
  C: { city_NESW: ['N', 'E', 'S', 'W'] },
  D: { city_N: ['N'], road_EW: ['E', 'W'], field_N: ['E:N', 'W:N'], field_S: ['S', 'E:S', 'W:S'] },
  E: { city_N: ['N'], field_ESW: ['E', 'S', 'W'] },
  F: { city_EW: ['E', 'W'], field_N: ['N'], field_S: ['S'] },
  G: { city_NS: ['N', 'S'], field_E: ['E'], field_W: ['W'] },
  H: { city_N: ['N'], city_S: ['S'], field_E: ['E'], field_W: ['W'] },
  I: { city_N: ['N'], city_W: ['W'], field_ES: ['E', 'S'] },
  J: { city_N: ['N'], road_ES: ['E', 'S'], field_W: ['W', 'E:N', 'S:W'], field_ES: ['E:S', 'S:E'] },
  K: { city_N: ['N'], road_SW: ['S', 'W'], field_E: ['E', 'S:E', 'W:N'], field_SW: ['S:W', 'W:S'] },
  L: { city_N: ['N'], road_E: ['E'], road_S: ['S'], road_W: ['W'], field_NE: ['E:N'], field_SE: ['E:S', 'S:E'], field_SW: ['S:W', 'W:S'], field_NW: ['W:N'] },
  M: { city_NW: ['N', 'W'], field_ES: ['E', 'S'] },
  N: { city_NW: ['N', 'W'], field_ES: ['E', 'S'] },
  O: { city_NW: ['N', 'W'], road_ES: ['E', 'S'], field_NE: ['E:N', 'S:W'], field_SE: ['E:S', 'S:E'] },
  P: { city_NW: ['N', 'W'], road_ES: ['E', 'S'], field_NE: ['E:N', 'S:W'], field_SE: ['E:S', 'S:E'] },
  Q: { city_NEW: ['N', 'E', 'W'], field_S: ['S'] },
  R: { city_NEW: ['N', 'E', 'W'], road_S: ['S'], field_SW: ['S:W'], field_SE: ['S:E'] },
  S: { city_NEW: ['N', 'E', 'W'], field_S: ['S'] },
  T: { city_NEW: ['N', 'E', 'W'], road_S: ['S'], field_SW: ['S:W'], field_SE: ['S:E'] },
  U: { road_NS: ['N', 'S'], field_E: ['E', 'N:E', 'S:E'], field_W: ['W', 'N:W', 'S:W'] },
  V: { road_SW: ['S', 'W'], field_NE: ['N', 'E', 'S:E', 'W:N'], field_SW: ['S:W', 'W:S'] },
  W: { road_N: ['N'], road_S: ['S'], road_W: ['W'], field_NE: ['E', 'N:E', 'S:E'], field_SE: ['E', 'N:E', 'S:E'], field_NW: ['N:W', 'W:N'], field_SW: ['S:W', 'W:S'] },
  X: { road_N: ['N'], road_E: ['E'], road_S: ['S'], road_W: ['W'], field_NE: ['N:E', 'E:N'], field_SE: ['E:S', 'S:E'], field_SW: ['S:W', 'W:S'], field_NW: ['W:N', 'N:W'] },
};

const OPPOSITE_DIR: Record<string, string> = { N: 'S', S: 'N', E: 'W', W: 'E' };
const DIR_OFFSET: Record<string, [number, number]> = {
  N: [0, 1], S: [0, -1], E: [1, 0], W: [-1, 0],
};

/** Rotate a compound edge like "S:E" or simple edge like "N" by rotation degrees. */
function rotateCompoundEdge(edge: string, rotation: number): string {
  if (edge.includes(':')) {
    const [dir, side] = edge.split(':');
    return `${rotateDirection(dir, rotation)}:${rotateDirection(side, rotation)}`;
  }
  return rotateDirection(edge, rotation);
}

/** Get the opposite compound edge: "E:N" → "W:N" (same side, opposite direction). */
function getOppositeEdge(edge: string): string {
  if (edge.includes(':')) {
    const [dir, side] = edge.split(':');
    return `${OPPOSITE_DIR[dir]}:${side}`;
  }
  return OPPOSITE_DIR[edge];
}

/**
 * Check if a meeple spot would connect to an already-occupied feature
 * by looking at adjacent tiles' features through their open_edges.
 *
 * Uses actual compound edge data from TILE_SPOT_EDGES (mirroring the backend)
 * and matches against feature open_edges for precise adjacency detection.
 */
function isSpotOccupiedByAdjacentFeature(
  spotEdges: string[],
  position: { x: number; y: number },
  gameData: CarcassonneGameData,
): boolean {
  console.log('[meeple-check] Checking spot edges:', spotEdges, 'at position:', position);
  for (const edge of spotEdges) {
    const dir = edge.split(':')[0];
    const [dx, dy] = DIR_OFFSET[dir];
    const neighborKey = `${position.x + dx},${position.y + dy}`;

    if (!gameData.board.tiles[neighborKey]) {
      console.log('[meeple-check]   edge', edge, '→ no neighbor at', neighborKey);
      continue;
    }

    const oppositeEdge = getOppositeEdge(edge);
    console.log('[meeple-check]   edge', edge, '→ neighbor at', neighborKey, ', looking for open_edge', [neighborKey, oppositeEdge]);

    // Search features for one with an open edge at [neighborKey, oppositeEdge]
    // that already has meeples placed on it
    let featuresWithMeeples = 0;
    for (const [fid, feature] of Object.entries(gameData.features)) {
      if (feature.meeples.length === 0) continue;
      featuresWithMeeples++;

      const openEdges = (feature as Record<string, unknown>).open_edges as string[][] | undefined;
      if (!openEdges) {
        console.log('[meeple-check]     feature', fid, 'has meeples but NO open_edges property!');
        continue;
      }

      const hasMatch = openEdges.some(
        (oe) => oe[0] === neighborKey && oe[1] === oppositeEdge
      );
      if (hasMatch) {
        console.log('[meeple-check]     MATCH! Feature', fid, 'has meeples and open_edge', [neighborKey, oppositeEdge]);
        return true;
      } else {
        console.log('[meeple-check]     feature', fid, 'has meeples, open_edges:', JSON.stringify(openEdges), '→ no match');
      }
    }
    if (featuresWithMeeples === 0) {
      console.log('[meeple-check]     No features with meeples found');
    }
  }

  console.log('[meeple-check] → NOT occupied');
  return false;
}

export const TILE_MEEPLE_PLACEMENTS: Record<string, MeeplePlacementDef[]> = {
  A: [
    { column: 0, row: 0, type: MEEPLE_TYPE_MONASTERY },
    { column: 20, row: -20, type: MEEPLE_TYPE_FIELD },
    { column: 0, row: 25, type: MEEPLE_TYPE_ROAD },
  ],
  B: [
    { column: 0, row: 0, type: MEEPLE_TYPE_MONASTERY },
    { column: 20, row: -20, type: MEEPLE_TYPE_FIELD },
  ],
  C: [
    { column: 0, row: 0, type: MEEPLE_TYPE_CITY },
  ],
  D: [
    { column: 0, row: -22, type: MEEPLE_TYPE_CITY },
    { column: -15, row: -9, type: MEEPLE_TYPE_FIELD },
    { column: 15, row: 16, type: MEEPLE_TYPE_FIELD },
    { column: -3, row: 7, type: MEEPLE_TYPE_ROAD },
  ],
  E: [
    { column: 0, row: -22, type: MEEPLE_TYPE_CITY },
    { column: 0, row: 10, type: MEEPLE_TYPE_FIELD },
  ],
  F: [
    { column: 0, row: 0, type: MEEPLE_TYPE_CITY },
    { column: 0, row: -22, type: MEEPLE_TYPE_FIELD },
    { column: 0, row: 26, type: MEEPLE_TYPE_FIELD },
  ],
  G: [
    { column: 0, row: 0, type: MEEPLE_TYPE_CITY },
    { column: 26, row: 0, type: MEEPLE_TYPE_FIELD },
    { column: -22, row: 0, type: MEEPLE_TYPE_FIELD },
  ],
  H: [
    { column: 0, row: -22, type: MEEPLE_TYPE_CITY },
    { column: 0, row: 22, type: MEEPLE_TYPE_CITY },
    { column: 0, row: 0, type: MEEPLE_TYPE_FIELD },
  ],
  I: [
    { column: 0, row: -22, type: MEEPLE_TYPE_CITY },
    { column: -22, row: 0, type: MEEPLE_TYPE_CITY },
    { column: 5, row: 5, type: MEEPLE_TYPE_FIELD },
  ],
  J: [
    { column: 0, row: -22, type: MEEPLE_TYPE_CITY },
    { column: -22, row: -4, type: MEEPLE_TYPE_FIELD },
    { column: 22, row: 22, type: MEEPLE_TYPE_FIELD },
    { column: 2, row: 2, type: MEEPLE_TYPE_ROAD },
  ],
  K: [
    { column: 0, row: -22, type: MEEPLE_TYPE_CITY },
    { column: 22, row: 10, type: MEEPLE_TYPE_FIELD },
    { column: -15, row: 15, type: MEEPLE_TYPE_FIELD },
    { column: 7, row: -2, type: MEEPLE_TYPE_ROAD },
  ],
  L: [
    { column: 0, row: -22, type: MEEPLE_TYPE_CITY },
    { column: -25, row: -15, type: MEEPLE_TYPE_FIELD },
    { column: -20, row: 20, type: MEEPLE_TYPE_FIELD },
    { column: 20, row: 20, type: MEEPLE_TYPE_FIELD },
    { column: 22, row: 0, type: MEEPLE_TYPE_ROAD },
    { column: -22, row: 0, type: MEEPLE_TYPE_ROAD },
    { column: 0, row: 22, type: MEEPLE_TYPE_ROAD },
  ],
  M: [
    { column: -12, row: -12, type: MEEPLE_TYPE_CITY },
    { column: 12, row: 12, type: MEEPLE_TYPE_FIELD },
  ],
  N: [
    { column: -12, row: -12, type: MEEPLE_TYPE_CITY },
    { column: 12, row: 12, type: MEEPLE_TYPE_FIELD },
  ],
  O: [
    { column: -12, row: -12, type: MEEPLE_TYPE_CITY },
    { column: -12, row: 20, type: MEEPLE_TYPE_FIELD },
    { column: 22, row: 22, type: MEEPLE_TYPE_FIELD },
    { column: 9, row: 9, type: MEEPLE_TYPE_ROAD },
  ],
  P: [
    { column: -12, row: -12, type: MEEPLE_TYPE_CITY },
    { column: -12, row: 20, type: MEEPLE_TYPE_FIELD },
    { column: 22, row: 22, type: MEEPLE_TYPE_FIELD },
    { column: 9, row: 9, type: MEEPLE_TYPE_ROAD },
  ],
  Q: [
    { column: 0, row: -10, type: MEEPLE_TYPE_CITY },
    { column: 0, row: 22, type: MEEPLE_TYPE_FIELD },
  ],
  R: [
    { column: 0, row: -10, type: MEEPLE_TYPE_CITY },
    { column: -15, row: 23, type: MEEPLE_TYPE_FIELD },
    { column: 15, row: 23, type: MEEPLE_TYPE_FIELD },
    { column: 0, row: 20, type: MEEPLE_TYPE_ROAD },
  ],
  S: [
    { column: 0, row: -10, type: MEEPLE_TYPE_CITY },
    { column: 0, row: 22, type: MEEPLE_TYPE_FIELD },
  ],
  T: [
    { column: 0, row: -10, type: MEEPLE_TYPE_CITY },
    { column: -15, row: 23, type: MEEPLE_TYPE_FIELD },
    { column: 15, row: 23, type: MEEPLE_TYPE_FIELD },
    { column: 0, row: 20, type: MEEPLE_TYPE_ROAD },
  ],
  U: [
    { column: 19, row: 0, type: MEEPLE_TYPE_FIELD },
    { column: -19, row: 0, type: MEEPLE_TYPE_FIELD },
    { column: 0, row: 0, type: MEEPLE_TYPE_ROAD },
  ],
  V: [
    { column: 10, row: -10, type: MEEPLE_TYPE_FIELD },
    { column: -20, row: 17, type: MEEPLE_TYPE_FIELD },
    { column: -10, row: 5, type: MEEPLE_TYPE_ROAD },
  ],
  W: [
    { column: 20, row: -20, type: MEEPLE_TYPE_FIELD },
    { column: 20, row: 20, type: MEEPLE_TYPE_FIELD },
    { column: -20, row: -20, type: MEEPLE_TYPE_FIELD },
    { column: -20, row: 20, type: MEEPLE_TYPE_FIELD },
    { column: 0, row: -20, type: MEEPLE_TYPE_ROAD },
    { column: 0, row: 20, type: MEEPLE_TYPE_ROAD },
    { column: -20, row: 0, type: MEEPLE_TYPE_ROAD },
  ],
  X: [
    { column: -20, row: -20, type: MEEPLE_TYPE_FIELD },
    { column: 20, row: -20, type: MEEPLE_TYPE_FIELD },
    { column: -20, row: 20, type: MEEPLE_TYPE_FIELD },
    { column: 20, row: 20, type: MEEPLE_TYPE_FIELD },
    { column: 20, row: 0, type: MEEPLE_TYPE_ROAD },
    { column: -20, row: 0, type: MEEPLE_TYPE_ROAD },
    { column: 0, row: 20, type: MEEPLE_TYPE_ROAD },
    { column: 0, row: -20, type: MEEPLE_TYPE_ROAD },
  ],
};

/**
 * Base (rotation=0) meeple spot names for each tile type.
 * Order matches TILE_MEEPLE_PLACEMENTS entries for that tile.
 * Names come from the backend's TILE_CATALOG meeple_spots.
 */
export const TILE_MEEPLE_SPOT_NAMES: Record<string, string[]> = {
  A: ['monastery', 'field_NEW', 'road_S'],
  B: ['monastery', 'field_NESW'],
  C: ['city_NESW'],
  D: ['city_N', 'field_N', 'field_S', 'road_EW'],
  E: ['city_N', 'field_ESW'],
  F: ['city_EW', 'field_N', 'field_S'],
  G: ['city_NS', 'field_E', 'field_W'],
  H: ['city_N', 'city_S', 'field_E'],
  I: ['city_N', 'city_W', 'field_ES'],
  J: ['city_N', 'field_W', 'field_ES', 'road_ES'],
  K: ['city_N', 'field_E', 'field_SW', 'road_SW'],
  L: ['city_N', 'field_NW', 'field_SW', 'field_SE', 'road_E', 'road_W', 'road_S'],
  M: ['city_NW', 'field_ES'],
  N: ['city_NW', 'field_ES'],
  O: ['city_NW', 'field_NE', 'field_SE', 'road_ES'],
  P: ['city_NW', 'field_NE', 'field_SE', 'road_ES'],
  Q: ['city_NEW', 'field_S'],
  R: ['city_NEW', 'field_SW', 'field_SE', 'road_S'],
  S: ['city_NEW', 'field_S'],
  T: ['city_NEW', 'field_SW', 'field_SE', 'road_S'],
  U: ['field_E', 'field_W', 'road_NS'],
  V: ['field_NE', 'field_SW', 'road_SW'],
  W: ['field_NE', 'field_SE', 'field_NW', 'field_SW', 'road_N', 'road_S', 'road_W'],
  X: ['field_NW', 'field_NE', 'field_SW', 'field_SE', 'road_E', 'road_W', 'road_S', 'road_N'],
};

/**
 * Rotate meeple placement pixel coordinates (from carcassonne-react).
 * Each 90-degree clockwise rotation: (col, row) -> (-row, col)
 */
export function rotateMeeplePlacement(
  placement: MeeplePlacementDef,
  rotation: number, // 0, 90, 180, 270
): MeeplePlacementDef {
  const steps = ((rotation / 90) | 0) % 4;
  let col = placement.column;
  let row = placement.row;
  for (let i = 0; i < steps; i++) {
    const temp = col;
    col = -row;
    row = temp;
  }
  return { ...placement, column: col, row };
}

const DIRECTIONS = ['N', 'E', 'S', 'W'];

function rotateDirection(dir: string, rotation: number): string {
  const steps = ((rotation / 90) | 0) % 4;
  const idx = DIRECTIONS.indexOf(dir);
  if (idx === -1) return dir;
  return DIRECTIONS[(idx + steps) % 4];
}

/**
 * Rotate a meeple spot name by rotating its direction components.
 * e.g. rotateMeepleSpotName('city_N', 90) => 'city_E'
 *      rotateMeepleSpotName('road_EW', 90) => 'road_NS'
 */
export function rotateMeepleSpotName(spot: string, rotation: number): string {
  if (rotation === 0) return spot;

  const parts = spot.split('_');
  if (parts.length < 2) return spot; // e.g. "monastery"

  const prefix = parts[0];
  const directionPart = parts[1];
  const suffix = parts.slice(2).join('_');

  const dirOrder: Record<string, number> = { N: 0, E: 1, S: 2, W: 3 };

  let rotated = '';
  for (const ch of directionPart) {
    if (ch in dirOrder) {
      rotated += rotateDirection(ch, rotation);
    } else {
      rotated += ch;
    }
  }
  // Sort direction letters into canonical order (N, E, S, W)
  rotated = rotated.split('').sort((a, b) => (dirOrder[a] ?? 99) - (dirOrder[b] ?? 99)).join('');

  let result = `${prefix}_${rotated}`;
  if (suffix) result += `_${suffix}`;
  return result;
}

export interface MeepleSpotInfo {
  spot: string;       // rotated spot name
  column: number;     // pixel offset X from tile center
  row: number;        // pixel offset Y from tile center
  type: number;       // meeple placement type
  edges: string[];    // rotated compound edges this spot connects through
}

/**
 * Get all meeple spots for a tile at a given rotation, with rotated pixel positions
 * and rotated spot names.
 */
export function getMeepleSpotsForTile(
  tileType: string,
  rotation: number,
): MeepleSpotInfo[] {
  const placements = TILE_MEEPLE_PLACEMENTS[tileType];
  const spotNames = TILE_MEEPLE_SPOT_NAMES[tileType];
  if (!placements || !spotNames) return [];

  return placements.map((placement, i) => {
    const rotated = rotateMeeplePlacement(placement, rotation);
    const baseSpotName = spotNames[i];
    const spotName = rotateMeepleSpotName(baseSpotName, rotation);
    const baseEdges = TILE_SPOT_EDGES[tileType]?.[baseSpotName] ?? [];
    const rotatedEdges = baseEdges.map(e => rotateCompoundEdge(e, rotation));
    return {
      spot: spotName,
      column: rotated.column,
      row: rotated.row,
      type: rotated.type,
      edges: rotatedEdges,
    };
  });
}

/**
 * Filter meeple spots to only those that are valid (feature not already occupied).
 * Uses tile_feature_map and features from game data for client-side validation.
 *
 * When the tile hasn't been placed yet (optimistic phase), checks adjacent tiles'
 * features through shared edges to determine if a spot would connect to an
 * already-occupied feature.
 */
export function getValidMeepleSpots(
  tileType: string,
  rotation: number,
  position: { x: number; y: number },
  gameData: CarcassonneGameData,
  playerId: string,
): MeepleSpotInfo[] {
  // Check if player has meeples available
  const supply = gameData.meeple_supply[playerId] ?? 0;
  if (supply <= 0) return [];

  const allSpots = getMeepleSpotsForTile(tileType, rotation);
  const posKey = `${position.x},${position.y}`;
  const tileFeatures = gameData.tile_feature_map[posKey];

  if (tileFeatures) {
    // Tile already placed — use server's feature map for exact validation
    return allSpots.filter((spotInfo) => {
      const featureId = tileFeatures[spotInfo.spot];
      if (!featureId) return true;
      const feature = gameData.features[featureId];
      if (!feature) return true;
      return feature.meeples.length === 0;
    });
  }

  // Tile not yet placed (optimistic phase) — check adjacent features via open_edges
  return allSpots.filter((spotInfo) => {
    return !isSpotOccupiedByAdjacentFeature(spotInfo.edges, position, gameData);
  });
}
