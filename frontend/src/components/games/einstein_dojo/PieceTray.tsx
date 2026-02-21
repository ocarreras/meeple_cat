'use client';

import { useRef, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { hexToPixel, kitePolygon } from '@/lib/hexGeometry';
import { ALL_ORIENTATIONS, orientationInfo } from '@/lib/einsteinPieces';

interface PieceTrayProps {
  currentOrientation: number;
  tilesRemaining: number;
  onRotate: () => void;
  onFlip: () => void;
  onDragStart: () => void;
  isMyTurn: boolean;
  isDragging: boolean;
  playerColor: string;
}

const PREVIEW_SIZE = 18;


export default function PieceTray({
  currentOrientation,
  tilesRemaining,
  onRotate,
  onFlip,
  onDragStart,
  isMyTurn,
  isDragging,
  playerColor,
}: PieceTrayProps) {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { chirality, rotation } = orientationInfo(currentOrientation);

  // Track click vs drag on the piece canvas
  const pointerStartRef = useRef<{ x: number; y: number; time: number } | null>(null);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (!isMyTurn) return;
      if (e.key === 'r' || e.key === 'R') {
        e.preventDefault();
        onRotate();
      } else if (e.key === 'f' || e.key === 'F') {
        e.preventDefault();
        onFlip();
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [isMyTurn, onRotate, onFlip]);

  // Render piece preview
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;

    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    if (isDragging) {
      // Show dimmed placeholder when dragging
      ctx.fillStyle = '#f3f4f6';
      ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = '#9ca3af';
      ctx.font = '12px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(t('game.dragging', 'Dragging...'), w / 2, h / 2);
      return;
    }

    const footprint = ALL_ORIENTATIONS[currentOrientation];

    // Bounding box of hex centers (for centering in canvas)
    const hexCenters = footprint.map(([q, r]) => hexToPixel(q, r, PREVIEW_SIZE));
    const minX = Math.min(...hexCenters.map(c => c.x)) - PREVIEW_SIZE;
    const maxX = Math.max(...hexCenters.map(c => c.x)) + PREVIEW_SIZE;
    const minY = Math.min(...hexCenters.map(c => c.y)) - PREVIEW_SIZE;
    const maxY = Math.max(...hexCenters.map(c => c.y)) + PREVIEW_SIZE;

    const pieceW = maxX - minX;
    const pieceH = maxY - minY;
    const offsetX = (w - pieceW) / 2 - minX;
    const offsetY = (h - pieceH) / 2 - minY;

    ctx.save();
    ctx.translate(offsetX, offsetY);

    for (const [q, r, k] of footprint) {
      const { x: cx, y: cy } = hexToPixel(q, r, PREVIEW_SIZE);
      const poly = kitePolygon(cx, cy, PREVIEW_SIZE, k);
      ctx.beginPath();
      ctx.moveTo(poly[0].x, poly[0].y);
      for (let i = 1; i < poly.length; i++) ctx.lineTo(poly[i].x, poly[i].y);
      ctx.closePath();
      ctx.fillStyle = playerColor;
      ctx.globalAlpha = 0.7;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = playerColor;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    ctx.restore();
  }, [currentOrientation, playerColor, isDragging, t]);

  // Pointer down on piece canvas — start tracking
  const handlePointerDown = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!isMyTurn) return;
    pointerStartRef.current = { x: e.clientX, y: e.clientY, time: Date.now() };
  }, [isMyTurn]);

  // Pointer move — if moved enough, start drag
  const handlePointerMove = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!pointerStartRef.current || isDragging) return;
    const dx = e.clientX - pointerStartRef.current.x;
    const dy = e.clientY - pointerStartRef.current.y;
    if (Math.abs(dx) > 5 || Math.abs(dy) > 5) {
      pointerStartRef.current = null;
      onDragStart();
    }
  }, [isDragging, onDragStart]);

  // Pointer up — if didn't drag, treat as click (rotate)
  const handlePointerUp = useCallback(() => {
    if (pointerStartRef.current && !isDragging) {
      const elapsed = Date.now() - pointerStartRef.current.time;
      // Short click = rotate
      if (elapsed < 300) {
        onRotate();
      }
    }
    pointerStartRef.current = null;
  }, [isDragging, onRotate]);

  // Double-click to flip
  const handleDoubleClick = useCallback(() => {
    if (isMyTurn) onFlip();
  }, [isMyTurn, onFlip]);

  return (
    <div className="bg-white rounded-lg border shadow-sm p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-semibold">{t('game.yourPiece', 'Your Piece')}</span>
        <span className="text-xs text-gray-500">
          {chirality === 'A' ? t('game.hat') : t('game.shirt')} · R{rotation}
        </span>
      </div>

      <div className="flex items-center gap-3">
        <canvas
          ref={canvasRef}
          width={120}
          height={100}
          className={`border rounded bg-gray-50 select-none ${
            isMyTurn
              ? isDragging
                ? 'cursor-grabbing opacity-50'
                : 'cursor-grab'
              : 'opacity-50'
          }`}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onDoubleClick={handleDoubleClick}
          title={isMyTurn ? t('game.dragToPlace', 'Drag to board or click to rotate (R), double-click to flip (F)') : ''}
          style={{ touchAction: 'none' }}
        />

        <div className="flex flex-col gap-2">
          <button
            onClick={onRotate}
            disabled={!isMyTurn}
            className="px-3 py-1.5 text-xs font-medium bg-gray-100 hover:bg-gray-200 disabled:opacity-40 rounded border transition-colors"
            title="R"
          >
            {t('game.rotate', 'Rotate')}
          </button>
          <button
            onClick={onFlip}
            disabled={!isMyTurn}
            className="px-3 py-1.5 text-xs font-medium bg-gray-100 hover:bg-gray-200 disabled:opacity-40 rounded border transition-colors"
            title="F"
          >
            {t('game.flip', 'Flip')}
          </button>
        </div>
      </div>

      <div className="mt-2 flex items-center justify-between">
        <span className="text-sm text-gray-600">{t('game.tilesRemainingLabel', 'Tiles remaining')}</span>
        <span className="text-lg font-bold">{tilesRemaining}</span>
      </div>
    </div>
  );
}
