/**
 * Einstein hat tile geometry — TypeScript mirror of backend pieces.py.
 *
 * Each tile covers 8 kites across 3 hex cells (4+2+2 distribution).
 * Two chiralities (A = hat, B = shirt/mirror) × 6 rotations = 12 orientations.
 */

/** A kite is identified by (q, r, k) where (q,r) is the hex and k is kite index 0..5. */
export type Kite = [number, number, number]; // [q, r, k]
export type Footprint = Kite[];

/**
 * Piece A (hat) base footprint at anchor (0,0).
 * Hex(0,0): kites 1,2,3,4  |  Hex(-1,1): kites 4,5  |  Hex(-1,0): kites 0,1
 */
export const PIECE_A_BASE: Footprint = [
  [0, 0, 1], [0, 0, 2], [0, 0, 3], [0, 0, 4],
  [-1, 1, 4], [-1, 1, 5],
  [-1, 0, 0], [-1, 0, 1],
];

/**
 * Piece B (shirt) base footprint — vertical mirror of A.
 * Hex(0,0): kites 0,1,2,5  |  Hex(1,-1): kites 2,3  |  Hex(1,0): kites 4,5
 */
export const PIECE_B_BASE: Footprint = [
  [0, 0, 0], [0, 0, 1], [0, 0, 2], [0, 0, 5],
  [1, -1, 2], [1, -1, 3],
  [1, 0, 4], [1, 0, 5],
];

/** Rotate a footprint 60° clockwise: (q,r) → (-r, q+r), kite → (kite+1)%6. */
export function rotateFootprint(footprint: Footprint): Footprint {
  return footprint.map(([q, r, k]) => [-r, q + r, (k + 1) % 6]);
}

/** Mirror a footprint (A↔B): (q,r) → (-q, q+r), kite → (3-k+6)%6. */
export function mirrorFootprint(footprint: Footprint): Footprint {
  return footprint.map(([q, r, k]) => [-q, q + r, ((3 - k) % 6 + 6) % 6]);
}

/** All 12 orientations: [0..5] = A rotations, [6..11] = B rotations. */
export const ALL_ORIENTATIONS: Footprint[] = (() => {
  const orientations: Footprint[] = [];

  // A chirality: 6 rotations
  let fp: Footprint = [...PIECE_A_BASE];
  for (let i = 0; i < 6; i++) {
    orientations.push([...fp]);
    fp = rotateFootprint(fp);
  }

  // B chirality: 6 rotations
  fp = [...PIECE_B_BASE];
  for (let i = 0; i < 6; i++) {
    orientations.push([...fp]);
    fp = rotateFootprint(fp);
  }

  return orientations;
})();

export const NUM_ORIENTATIONS = 12;

/** Get chirality ("A"|"B") and rotation (0..5) from orientation index. */
export function orientationInfo(index: number): { chirality: "A" | "B"; rotation: number } {
  if (index < 6) return { chirality: "A", rotation: index };
  return { chirality: "B", rotation: index - 6 };
}

/** Get orientation index from chirality and rotation. */
export function orientationIndex(chirality: "A" | "B", rotation: number): number {
  return chirality === "A" ? rotation : rotation + 6;
}

/** Get the 8 absolute kite positions for a piece at given orientation and anchor. */
export function getPlacedKites(
  orientation: number,
  anchorQ: number,
  anchorR: number,
): Kite[] {
  const base = ALL_ORIENTATIONS[orientation];
  return base.map(([q, r, k]) => [q + anchorQ, r + anchorR, k]);
}

/** Get the set of hex cells occupied by a piece. */
export function getOccupiedHexes(
  orientation: number,
  anchorQ: number,
  anchorR: number,
): Set<string> {
  const kites = getPlacedKites(orientation, anchorQ, anchorR);
  const hexes = new Set<string>();
  for (const [q, r] of kites) {
    hexes.add(`${q},${r}`);
  }
  return hexes;
}

/** Build a kite key string matching backend format: "q,r:k". */
export function kiteToKey(q: number, r: number, k: number): string {
  return `${q},${r}:${k}`;
}

/**
 * Neighbor direction for each hex edge index (flat-top).
 * Edge i connects vertex i to vertex (i+1)%6 and faces the neighbor in this direction.
 */
const EDGE_DIRECTIONS: [number, number][] = [
  [1, 0],   // edge 0
  [0, 1],   // edge 1
  [-1, 1],  // edge 2
  [-1, 0],  // edge 3
  [0, -1],  // edge 4
  [1, -1],  // edge 5
];

/**
 * Return the 4 kites that share an edge with kite (q, r, k).
 *
 * Within the same hex, kite k shares edges with kites (k+1)%6 and (k+5)%6.
 * Across hex boundaries:
 *   - via hex edge (k+5)%6: kite (k+2)%6 in the neighbor across that edge
 *   - via hex edge k:       kite (k+4)%6 in the neighbor across that edge
 */
function kiteEdgeNeighbors(q: number, r: number, k: number): Kite[] {
  const prev = (k + 5) % 6;
  const next = (k + 1) % 6;
  const [dq1, dr1] = EDGE_DIRECTIONS[prev];
  const [dq2, dr2] = EDGE_DIRECTIONS[k];
  return [
    [q, r, next],                        // same hex, clockwise neighbor
    [q, r, prev],                        // same hex, counter-clockwise neighbor
    [q + dq1, r + dr1, (k + 2) % 6],    // cross-hex via edge (k-1)
    [q + dq2, r + dr2, (k + 4) % 6],    // cross-hex via edge k
  ];
}

/**
 * Client-side placement validation.
 * Checks: no kite overlap, adjacency to existing tiles (first piece exempt).
 */
export function isValidPlacement(
  kiteOwners: Record<string, string>,
  orientation: number,
  anchorQ: number,
  anchorR: number,
): boolean {
  if (orientation < 0 || orientation >= NUM_ORIENTATIONS) return false;

  const kites = getPlacedKites(orientation, anchorQ, anchorR);

  // Check no overlap
  for (const [q, r, k] of kites) {
    if (kiteToKey(q, r, k) in kiteOwners) return false;
  }

  // Check adjacency via shared kite edges (first placement exempt)
  if (Object.keys(kiteOwners).length > 0) {
    const hasAdjacentEdge = kites.some(([q, r, k]) =>
      kiteEdgeNeighbors(q, r, k).some(([nq, nr, nk]) =>
        kiteToKey(nq, nr, nk) in kiteOwners
      )
    );
    if (!hasAdjacentEdge) return false;
  }

  return true;
}

/**
 * Return set of hex keys where a mark can be placed.
 * Valid: adjacent to board (hex or neighbor has kites), not Complete, not Conflict,
 * and not already marked.
 */
export function getValidMarkHexes(
  kiteOwners: Record<string, string>,
  hexStates: Record<string, string>,
  hexMarks: Record<string, string>,
): Set<string> {
  // Gather occupied hex coords
  const occupied = new Set<string>();
  for (const key of Object.keys(kiteOwners)) {
    occupied.add(key.split(':')[0]);
  }

  // Candidates: occupied hexes + their neighbors
  const candidates = new Set<string>();
  for (const hexKey of occupied) {
    candidates.add(hexKey);
    const [q, r] = hexKey.split(',').map(Number);
    const dirs = [
      [1, 0], [1, -1], [0, -1],
      [-1, 0], [-1, 1], [0, 1],
    ];
    for (const [dq, dr] of dirs) {
      candidates.add(`${q + dq},${r + dr}`);
    }
  }

  // Filter
  const valid = new Set<string>();
  for (const hexKey of candidates) {
    const state = hexStates[hexKey] ?? 'empty';
    if (state === 'complete' || state === 'conflict') continue;
    if (hexKey in hexMarks) continue;
    valid.add(hexKey);
  }
  return valid;
}
