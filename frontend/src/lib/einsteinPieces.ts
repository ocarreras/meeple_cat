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

  // Check adjacency (first placement exempt)
  if (Object.keys(kiteOwners).length > 0) {
    const pieceHexes = new Set<string>();
    for (const [q, r] of kites) {
      pieceHexes.add(`${q},${r}`);
    }

    const occupiedHexes = new Set<string>();
    for (const key of Object.keys(kiteOwners)) {
      const hexPart = key.split(":")[0];
      occupiedHexes.add(hexPart);
    }

    let adjacent = false;
    for (const hex of pieceHexes) {
      if (occupiedHexes.has(hex)) {
        adjacent = true;
        break;
      }
    }

    if (!adjacent) return false;
  }

  return true;
}
