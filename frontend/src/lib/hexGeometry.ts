/**
 * Hex geometry utilities for flat-top hexagonal kite grid.
 *
 * Coordinate system: axial (q, r) with flat-top orientation.
 * Pixel center of hex (q, r):
 *   x = 3/2 * size * q
 *   y = sqrt(3) * size * (r + q/2)
 */

/** Convert axial hex coords to pixel center. */
export function hexToPixel(q: number, r: number, size: number): { x: number; y: number } {
  return {
    x: (3 / 2) * size * q,
    y: Math.sqrt(3) * size * (r + q / 2),
  };
}

/** Convert pixel coords to fractional axial hex coords. */
export function pixelToFractionalHex(
  px: number,
  py: number,
  size: number,
): { q: number; r: number } {
  const q = (2 / 3) * px / size;
  const r = (-1 / 3) * px / size + (Math.sqrt(3) / 3) * py / size;
  return { q, r };
}

/** Round fractional axial coords to nearest hex. */
export function axialRound(q: number, r: number): { q: number; r: number } {
  const s = -q - r;
  let rq = Math.round(q);
  let rr = Math.round(r);
  const rs = Math.round(s);

  const dq = Math.abs(rq - q);
  const dr = Math.abs(rr - r);
  const ds = Math.abs(rs - s);

  if (dq > dr && dq > ds) {
    rq = -rr - rs;
  } else if (dr > ds) {
    rr = -rq - rs;
  }

  return { q: rq, r: rr };
}

/** Convert pixel coords to the nearest hex (q, r). */
export function pixelToHex(px: number, py: number, size: number): { q: number; r: number } {
  const frac = pixelToFractionalHex(px, py, size);
  return axialRound(frac.q, frac.r);
}

/**
 * Get the i-th vertex of a flat-top hex centered at (cx, cy).
 * Vertex 0 is at the right (3 o'clock), going CCW.
 */
export function hexVertex(
  cx: number,
  cy: number,
  size: number,
  i: number,
): { x: number; y: number } {
  const angle = (Math.PI / 3) * i;
  return {
    x: cx + size * Math.cos(angle),
    y: cy + size * Math.sin(angle),
  };
}

/**
 * Get the midpoint of edge i of a flat-top hex.
 * Edge i connects vertex i and vertex (i+1)%6.
 */
export function hexEdgeMidpoint(
  cx: number,
  cy: number,
  size: number,
  i: number,
): { x: number; y: number } {
  const v1 = hexVertex(cx, cy, size, i);
  const v2 = hexVertex(cx, cy, size, (i + 1) % 6);
  return {
    x: (v1.x + v2.x) / 2,
    y: (v1.y + v2.y) / 2,
  };
}

/**
 * Get the 4 corners of kite `k` inside a flat-top hex centered at (cx, cy).
 *
 * Each hex has 6 kites (k = 0..5). Kite k is the quadrilateral:
 *   center → edge_midpoint(k) → vertex(k) → edge_midpoint((k+5)%6)
 *
 * This matches the backend convention where kite k is associated with vertex k.
 */
export function kitePolygon(
  cx: number,
  cy: number,
  size: number,
  k: number,
): { x: number; y: number }[] {
  const center = { x: cx, y: cy };
  const mid1 = hexEdgeMidpoint(cx, cy, size, k);
  const vertex = hexVertex(cx, cy, size, k);
  const mid2 = hexEdgeMidpoint(cx, cy, size, (k + 5) % 6);

  return [center, mid2, vertex, mid1];
}

/** Six axial direction vectors for flat-top hex grid. */
export const HEX_DIRECTIONS: [number, number][] = [
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
  [1, -1],
  [-1, 1],
];

/** Get the 6 neighbor coords of hex (q, r). */
export function hexNeighbors(q: number, r: number): { q: number; r: number }[] {
  return HEX_DIRECTIONS.map(([dq, dr]) => ({ q: q + dq, r: r + dr }));
}
