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
 * Base edge definitions for all tile types at rotation 0.
 * C=City, R=Road, F=Field.
 */
const TILE_EDGES: Record<string, Record<string, string>> = {
  A: { N: 'F', E: 'F', S: 'R', W: 'F' },
  B: { N: 'F', E: 'F', S: 'F', W: 'F' },
  C: { N: 'C', E: 'C', S: 'C', W: 'C' },
  D: { N: 'C', E: 'R', S: 'F', W: 'R' },
  E: { N: 'C', E: 'F', S: 'F', W: 'F' },
  F: { N: 'F', E: 'C', S: 'F', W: 'C' },
  G: { N: 'C', E: 'F', S: 'C', W: 'F' },
  H: { N: 'C', E: 'F', S: 'C', W: 'F' },
  I: { N: 'C', E: 'F', S: 'F', W: 'C' },
  J: { N: 'C', E: 'R', S: 'R', W: 'F' },
  K: { N: 'C', E: 'F', S: 'R', W: 'R' },
  L: { N: 'C', E: 'R', S: 'R', W: 'R' },
  M: { N: 'C', E: 'F', S: 'F', W: 'C' },
  N: { N: 'C', E: 'F', S: 'F', W: 'C' },
  O: { N: 'C', E: 'R', S: 'R', W: 'C' },
  P: { N: 'C', E: 'R', S: 'R', W: 'C' },
  Q: { N: 'C', E: 'C', S: 'F', W: 'C' },
  R: { N: 'C', E: 'C', S: 'R', W: 'C' },
  S: { N: 'C', E: 'C', S: 'F', W: 'C' },
  T: { N: 'C', E: 'C', S: 'R', W: 'C' },
  U: { N: 'R', E: 'F', S: 'R', W: 'F' },
  V: { N: 'F', E: 'F', S: 'R', W: 'R' },
  W: { N: 'R', E: 'F', S: 'R', W: 'R' },
  X: { N: 'R', E: 'R', S: 'R', W: 'R' },
};

function getRotatedEdges(tileType: string, rotation: number): Record<string, string> {
  const base = TILE_EDGES[tileType];
  if (!base) return {};
  const steps = ((rotation / 90) | 0) % 4;
  const result: Record<string, string> = {};
  for (let i = 0; i < 4; i++) {
    const sourceIdx = ((i - steps) % 4 + 4) % 4;
    result[DIRECTIONS[i]] = base[DIRECTIONS[sourceIdx]];
  }
  return result;
}

const OPPOSITE_DIR: Record<string, string> = { N: 'S', S: 'N', E: 'W', W: 'E' };
const DIR_OFFSET: Record<string, [number, number]> = {
  N: [0, 1], S: [0, -1], E: [1, 0], W: [-1, 0],
};

/**
 * Check if a meeple spot would connect to an already-occupied feature
 * by looking at adjacent tiles' features through shared edges.
 */
function isSpotOccupiedByAdjacentFeature(
  spotInfo: MeepleSpotInfo,
  position: { x: number; y: number },
  tileEdges: Record<string, string>,
  gameData: CarcassonneGameData,
): boolean {
  const parts = spotInfo.spot.split('_');
  if (parts.length < 2) return false; // monastery — no edge connections

  const featureType = parts[0]; // 'city', 'road', 'field'
  const dirPart = parts[1];
  const spotDirs = dirPart.split('').filter(ch => 'NESW'.includes(ch));

  // Map feature type to which edge types it connects through
  // City connects through C edges, road through R, field through F edges
  let edgeType: string;
  if (featureType === 'city') edgeType = 'C';
  else if (featureType === 'road') edgeType = 'R';
  else if (featureType === 'field') edgeType = 'F';
  else return false;

  for (const dir of spotDirs) {
    // Only check edges that match this feature type
    if (tileEdges[dir] !== edgeType) continue;

    const [dx, dy] = DIR_OFFSET[dir];
    const neighborKey = `${position.x + dx},${position.y + dy}`;
    const neighborFeatureMap = gameData.tile_feature_map[neighborKey];
    if (!neighborFeatureMap) continue;

    const oppositeDir = OPPOSITE_DIR[dir];

    // Find neighbor's feature of the same type touching the shared edge
    for (const [neighborSpot, featureId] of Object.entries(neighborFeatureMap)) {
      const neighborParts = neighborSpot.split('_');
      if (neighborParts.length < 2) continue;
      if (neighborParts[0] !== featureType) continue;

      const neighborDirs = neighborParts[1].split('').filter(ch => 'NESW'.includes(ch));
      if (!neighborDirs.includes(oppositeDir)) continue;

      const feature = gameData.features[featureId];
      if (feature && feature.meeples.length > 0) {
        return true;
      }
    }
  }

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
  W: ['field_NE', 'field_SE', 'field_NW', 'road_N', 'road_S', 'road_W'],
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
    const spotName = rotateMeepleSpotName(spotNames[i], rotation);
    return {
      spot: spotName,
      column: rotated.column,
      row: rotated.row,
      type: rotated.type,
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

  // Tile not yet placed (optimistic phase) — check adjacent features
  const tileEdges = getRotatedEdges(tileType, rotation);
  return allSpots.filter((spotInfo) => {
    return !isSpotOccupiedByAdjacentFeature(spotInfo, position, tileEdges, gameData);
  });
}
