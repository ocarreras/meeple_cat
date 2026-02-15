'use client';

import { useEffect, useRef, useState, useCallback, useImperativeHandle, forwardRef } from 'react';
import { useTranslation } from 'react-i18next';
import { EinsteinDojoGameData, Player } from '@/lib/types';
import { hexToPixel, hexVertex, hexEdgeMidpoint, kitePolygon } from '@/lib/hexGeometry';
import { getPlacedKites } from '@/lib/einsteinPieces';

export interface GhostPiece {
  orientation: number;
  anchorQ: number;
  anchorR: number;
  valid: boolean;
}

export interface BoardHandle {
  screenToHex: (clientX: number, clientY: number) => { q: number; r: number } | null;
}

interface EinsteinDojoBoardProps {
  gameData: EinsteinDojoGameData;
  players: Player[];
  onHexClicked: (q: number, r: number) => void;
  onHoverHex: (q: number, r: number) => void;
  onHoverLeave: () => void;
  isMyTurn: boolean;
  phase: string;
  ghostPiece: GhostPiece | null;
}

const HEX_SIZE = 40;
const PLAYER_COLORS = ['#3b82f6', '#f97316'];
const PLAYER_FILL_COLORS = ['rgba(59, 130, 246, 0.6)', 'rgba(249, 115, 22, 0.6)'];
const GHOST_VALID_COLOR = 'rgba(34, 197, 94, 0.45)';
const GHOST_INVALID_COLOR = 'rgba(156, 163, 175, 0.25)';

interface Camera {
  x: number;
  y: number;
  zoom: number;
}

function getTouchDistance(t1: Touch, t2: Touch): number {
  return Math.sqrt(
    Math.pow(t1.clientX - t2.clientX, 2) + Math.pow(t1.clientY - t2.clientY, 2)
  );
}

function clientToHex(
  clientX: number,
  clientY: number,
  canvas: HTMLCanvasElement,
  camera: Camera,
): { q: number; r: number } {
  const rect = canvas.getBoundingClientRect();
  const canvasX = clientX - rect.left;
  const canvasY = clientY - rect.top;
  const worldX = (canvasX - canvas.width / 2 - camera.x) / camera.zoom;
  const worldY = (canvasY - canvas.height / 2 - camera.y) / camera.zoom;

  const q = (2 / 3) * worldX / HEX_SIZE;
  const r = (-1 / 3) * worldX / HEX_SIZE + (Math.sqrt(3) / 3) * worldY / HEX_SIZE;

  const s = -q - r;
  let rq = Math.round(q);
  let rr = Math.round(r);
  const rs = Math.round(s);
  const dq = Math.abs(rq - q);
  const dr = Math.abs(rr - r);
  const ds = Math.abs(rs - s);
  if (dq > dr && dq > ds) rq = -rr - rs;
  else if (dr > ds) rr = -rq - rs;

  return { q: rq, r: rr };
}

const EinsteinDojoBoard = forwardRef<BoardHandle, EinsteinDojoBoardProps>(function EinsteinDojoBoard(
  {
    gameData,
    players,
    onHexClicked,
    onHoverHex,
    onHoverLeave,
    isMyTurn,
    phase,
    ghostPiece,
  },
  ref,
) {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [camera, setCamera] = useState<Camera>({ x: 0, y: 0, zoom: 1.5 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });
  const [canvasDims, setCanvasDims] = useState({ width: 0, height: 0 });
  const [isTouchDevice, setIsTouchDevice] = useState(false);

  // Refs for touch/event handlers (avoid stale closures)
  const cameraRef = useRef(camera);
  cameraRef.current = camera;
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);
  const touchCameraStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const pinchDistRef = useRef<number | null>(null);
  const pinchZoomStartRef = useRef<number>(1);
  const touchMovedRef = useRef(false);

  const isMyTurnRef = useRef(isMyTurn);
  isMyTurnRef.current = isMyTurn;
  const phaseRef = useRef(phase);
  phaseRef.current = phase;
  const onHexClickedRef = useRef(onHexClicked);
  onHexClickedRef.current = onHexClicked;
  const onHoverHexRef = useRef(onHoverHex);
  onHoverHexRef.current = onHoverHex;

  // Expose screenToHex for cross-component drag
  useImperativeHandle(ref, () => ({
    screenToHex: (clientX: number, clientY: number) => {
      const canvas = canvasRef.current;
      if (!canvas) return null;
      return clientToHex(clientX, clientY, canvas, cameraRef.current);
    },
  }));

  const playerColorMap = useCallback(() => {
    const map: Record<string, number> = {};
    players.forEach(p => { map[p.player_id] = p.seat_index; });
    return map;
  }, [players]);

  // Resize observer
  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        canvas.width = width;
        canvas.height = height;
        setCanvasDims({ width, height });
      }
    });
    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, []);

  // Wheel zoom
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setCamera(prev => ({
        ...prev,
        zoom: Math.max(0.3, Math.min(5.0, prev.zoom - e.deltaY * 0.002)),
      }));
    };
    canvas.addEventListener('wheel', handleWheel, { passive: false });
    return () => canvas.removeEventListener('wheel', handleWheel);
  }, []);

  // Touch handlers
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const handleTouchStart = (e: TouchEvent) => {
      e.preventDefault();
      setIsTouchDevice(true);
      if (e.touches.length === 1) {
        const touch = e.touches[0];
        touchStartRef.current = { x: touch.clientX, y: touch.clientY };
        touchCameraStartRef.current = { x: cameraRef.current.x, y: cameraRef.current.y };
        touchMovedRef.current = false;
        pinchDistRef.current = null;
      } else if (e.touches.length === 2) {
        pinchDistRef.current = getTouchDistance(e.touches[0], e.touches[1]);
        pinchZoomStartRef.current = cameraRef.current.zoom;
        touchMovedRef.current = true;
      }
    };

    const handleTouchMove = (e: TouchEvent) => {
      e.preventDefault();
      if (e.touches.length === 2 && pinchDistRef.current !== null) {
        const newDist = getTouchDistance(e.touches[0], e.touches[1]);
        const scale = newDist / pinchDistRef.current;
        const newZoom = Math.max(0.3, Math.min(5.0, pinchZoomStartRef.current * scale));
        setCamera(prev => ({ ...prev, zoom: newZoom }));
      } else if (e.touches.length === 1 && touchStartRef.current) {
        const touch = e.touches[0];
        const dx = touch.clientX - touchStartRef.current.x;
        const dy = touch.clientY - touchStartRef.current.y;
        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) touchMovedRef.current = true;
        setCamera(prev => ({
          ...prev,
          x: touchCameraStartRef.current.x + dx,
          y: touchCameraStartRef.current.y + dy,
        }));
      }
    };

    const handleTouchEnd = (e: TouchEvent) => {
      e.preventDefault();
      if (!touchMovedRef.current && touchStartRef.current && e.changedTouches.length === 1) {
        const touch = e.changedTouches[0];
        if (isMyTurnRef.current && phaseRef.current === 'place_tile') {
          const hex = clientToHex(touch.clientX, touch.clientY, canvas, cameraRef.current);
          onHexClickedRef.current(hex.q, hex.r);
        }
      }
      touchStartRef.current = null;
      pinchDistRef.current = null;
    };

    canvas.addEventListener('touchstart', handleTouchStart, { passive: false });
    canvas.addEventListener('touchmove', handleTouchMove, { passive: false });
    canvas.addEventListener('touchend', handleTouchEnd, { passive: false });
    return () => {
      canvas.removeEventListener('touchstart', handleTouchStart);
      canvas.removeEventListener('touchmove', handleTouchMove);
      canvas.removeEventListener('touchend', handleTouchEnd);
    };
  }, []);

  // Mouse handlers — pan + hover + click
  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    setIsPanning(true);
    setPanStart({ x: e.clientX - camera.x, y: e.clientY - camera.y });
  }, [camera]);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (isPanning) {
      setCamera(prev => ({
        ...prev,
        x: e.clientX - panStart.x,
        y: e.clientY - panStart.y,
      }));
    } else if (isMyTurn && phase === 'place_tile') {
      // Report hover hex for ghost preview (only when not panning)
      const canvas = canvasRef.current;
      if (canvas) {
        const hex = clientToHex(e.clientX, e.clientY, canvas, camera);
        onHoverHex(hex.q, hex.r);
      }
    }
  }, [isPanning, panStart, isMyTurn, phase, camera, onHoverHex]);

  const handleMouseUp = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (isPanning) {
      const dragDistance = Math.sqrt(
        Math.pow(e.clientX - (panStart.x + camera.x), 2) +
        Math.pow(e.clientY - (panStart.y + camera.y), 2)
      );
      if (dragDistance < 5 && isMyTurn && phase === 'place_tile') {
        const canvas = canvasRef.current;
        if (canvas) {
          const hex = clientToHex(e.clientX, e.clientY, canvas, camera);
          onHexClicked(hex.q, hex.r);
        }
      }
    }
    setIsPanning(false);
  }, [isPanning, panStart, camera, isMyTurn, phase, onHexClicked]);

  const handleMouseLeave = useCallback(() => {
    setIsPanning(false);
    onHoverLeave();
  }, [onHoverLeave]);

  // ─── Render ───
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    if (canvasDims.width === 0 || canvasDims.height === 0) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    ctx.translate(canvas.width / 2 + camera.x, canvas.height / 2 + camera.y);
    ctx.scale(camera.zoom, camera.zoom);

    const colors = playerColorMap();

    // ── Hex grid ──
    const occupiedHexes = new Set<string>();
    for (const key of Object.keys(gameData.board.kite_owners)) {
      occupiedHexes.add(key.split(':')[0]);
    }

    const gridHexes = new Set<string>();
    if (occupiedHexes.size === 0) {
      for (let q = -3; q <= 3; q++) {
        for (let r = -3; r <= 3; r++) {
          gridHexes.add(`${q},${r}`);
        }
      }
    } else {
      for (const hexKey of occupiedHexes) {
        const [hq, hr] = hexKey.split(',').map(Number);
        for (let dq = -2; dq <= 2; dq++) {
          for (let dr = -2; dr <= 2; dr++) {
            gridHexes.add(`${hq + dq},${hr + dr}`);
          }
        }
      }
    }

    ctx.strokeStyle = '#d1d5db';
    ctx.lineWidth = 0.5;
    for (const hexKey of gridHexes) {
      const [q, r] = hexKey.split(',').map(Number);
      const { x: cx, y: cy } = hexToPixel(q, r, HEX_SIZE);
      drawHexOutline(ctx, cx, cy, HEX_SIZE);
      // Draw kite dividers (center → vertices and center → edge midpoints)
      drawKiteDividers(ctx, cx, cy, HEX_SIZE);
    }

    // ── Placed pieces ──
    for (const piece of gameData.board.placed_pieces) {
      const seatIdx = colors[piece.player_id] ?? 0;
      const fillColor = PLAYER_FILL_COLORS[seatIdx % PLAYER_FILL_COLORS.length];
      const strokeColor = PLAYER_COLORS[seatIdx % PLAYER_COLORS.length];

      const kites = getPlacedKites(piece.orientation, piece.anchor_q, piece.anchor_r);
      for (const [q, r, k] of kites) {
        const { x: cx, y: cy } = hexToPixel(q, r, HEX_SIZE);
        drawKite(ctx, cx, cy, HEX_SIZE, k, fillColor, strokeColor, 1.5);
      }
    }

    // ── Hex state overlays ──
    for (const [hexKey, state] of Object.entries(gameData.board.hex_states)) {
      const [q, r] = hexKey.split(',').map(Number);
      const { x: cx, y: cy } = hexToPixel(q, r, HEX_SIZE);

      if (state === 'complete') {
        const sampleKiteKey = `${hexKey}:0`;
        const owner = gameData.board.kite_owners[sampleKiteKey];
        const seatIdx = owner ? (colors[owner] ?? 0) : 0;
        // Subtle fill to highlight completed hexes
        ctx.fillStyle = seatIdx === 0 ? 'rgba(59, 130, 246, 0.08)' : 'rgba(249, 115, 22, 0.08)';
        drawHexFill(ctx, cx, cy, HEX_SIZE * 0.92);
        ctx.strokeStyle = PLAYER_COLORS[seatIdx % PLAYER_COLORS.length];
        ctx.lineWidth = 3;
        drawHexOutline(ctx, cx, cy, HEX_SIZE * 0.92);
      } else if (state === 'conflict') {
        ctx.strokeStyle = '#ef4444';
        ctx.lineWidth = 2;
        ctx.setLineDash([4, 4]);
        drawHexOutline(ctx, cx, cy, HEX_SIZE * 0.92);
        ctx.setLineDash([]);
      }
    }

    // ── Ghost piece ──
    if (ghostPiece) {
      const kites = getPlacedKites(ghostPiece.orientation, ghostPiece.anchorQ, ghostPiece.anchorR);

      if (ghostPiece.valid) {
        ctx.shadowColor = '#22c55e';
        ctx.shadowBlur = 15;
      }

      const fillColor = ghostPiece.valid ? GHOST_VALID_COLOR : GHOST_INVALID_COLOR;
      const strokeColor = ghostPiece.valid ? '#22c55e' : '#9ca3af';

      for (const [q, r, k] of kites) {
        const { x: cx, y: cy } = hexToPixel(q, r, HEX_SIZE);
        drawKite(ctx, cx, cy, HEX_SIZE, k, fillColor, strokeColor, 1.5);
      }

      ctx.shadowColor = 'transparent';
      ctx.shadowBlur = 0;
    }

    ctx.restore();
  }, [camera, canvasDims, gameData, players, ghostPiece, playerColorMap]);

  return (
    <div ref={containerRef} className="w-full h-full bg-gray-100 relative overflow-hidden">
      <canvas
        ref={canvasRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        className={`w-full h-full ${isMyTurn && phase === 'place_tile' ? 'cursor-crosshair' : 'cursor-grab'} active:cursor-grabbing`}
        style={{ touchAction: 'none' }}
      />
      <div className="absolute bottom-2 left-2 md:bottom-4 md:left-4 bg-white/80 px-2 py-1 md:px-3 md:py-2 rounded shadow text-xs md:text-sm">
        <div>{t('game.zoom', { level: (camera.zoom * 100).toFixed(0) })}</div>
        <div className="text-xs text-gray-500">
          {isTouchDevice ? t('game.controlsTouch') : t('game.controlsMouse')}
        </div>
      </div>
    </div>
  );
});

export default EinsteinDojoBoard;

/** Draw a flat-top hexagon outline. */
function drawHexOutline(ctx: CanvasRenderingContext2D, cx: number, cy: number, size: number) {
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i;
    const vx = cx + size * Math.cos(angle);
    const vy = cy + size * Math.sin(angle);
    if (i === 0) ctx.moveTo(vx, vy);
    else ctx.lineTo(vx, vy);
  }
  ctx.closePath();
  ctx.stroke();
}

/** Fill a flat-top hexagon. */
function drawHexFill(ctx: CanvasRenderingContext2D, cx: number, cy: number, size: number) {
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i;
    const vx = cx + size * Math.cos(angle);
    const vy = cy + size * Math.sin(angle);
    if (i === 0) ctx.moveTo(vx, vy);
    else ctx.lineTo(vx, vy);
  }
  ctx.closePath();
  ctx.fill();
}

/** Draw kite dividers inside a hex (lines from center to vertices and edge midpoints). */
function drawKiteDividers(ctx: CanvasRenderingContext2D, cx: number, cy: number, size: number) {
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const v = hexVertex(cx, cy, size, i);
    ctx.moveTo(cx, cy);
    ctx.lineTo(v.x, v.y);
    const m = hexEdgeMidpoint(cx, cy, size, i);
    ctx.moveTo(cx, cy);
    ctx.lineTo(m.x, m.y);
  }
  ctx.stroke();
}

/** Draw a single kite quadrilateral. */
function drawKite(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, size: number, k: number,
  fillColor: string, strokeColor: string, lineWidth: number,
) {
  const poly = kitePolygon(cx, cy, size, k);
  ctx.beginPath();
  ctx.moveTo(poly[0].x, poly[0].y);
  for (let i = 1; i < poly.length; i++) ctx.lineTo(poly[i].x, poly[i].y);
  ctx.closePath();
  ctx.fillStyle = fillColor;
  ctx.fill();
  ctx.strokeStyle = strokeColor;
  ctx.lineWidth = lineWidth;
  ctx.stroke();
}
