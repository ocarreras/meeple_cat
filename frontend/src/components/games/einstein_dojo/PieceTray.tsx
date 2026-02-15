'use client';

import { useRef, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { hexToPixel, kitePolygon } from '@/lib/hexGeometry';
import { ALL_ORIENTATIONS, orientationInfo, NUM_ORIENTATIONS } from '@/lib/einsteinPieces';

interface PieceTrayProps {
  currentOrientation: number;
  tilesRemaining: number;
  onRotate: () => void;
  onFlip: () => void;
  isMyTurn: boolean;
  playerColor: string;
}

const PREVIEW_SIZE = 18;

export default function PieceTray({
  currentOrientation,
  tilesRemaining,
  onRotate,
  onFlip,
  isMyTurn,
  playerColor,
}: PieceTrayProps) {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { chirality, rotation } = orientationInfo(currentOrientation);

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

    const footprint = ALL_ORIENTATIONS[currentOrientation];

    // Find bounding box of hex centers to center the preview
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
      for (let i = 1; i < poly.length; i++) {
        ctx.lineTo(poly[i].x, poly[i].y);
      }
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
  }, [currentOrientation, playerColor]);

  return (
    <div className="bg-white rounded-lg border shadow-sm p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-semibold">{t('game.yourPiece', 'Your Piece')}</span>
        <span className="text-xs text-gray-500">
          {chirality === 'A' ? 'Hat' : 'Shirt'} · R{rotation}
        </span>
      </div>

      <div className="flex items-center gap-3">
        <canvas
          ref={canvasRef}
          width={120}
          height={100}
          className={`border rounded bg-gray-50 ${isMyTurn ? 'cursor-pointer' : 'opacity-50'}`}
          onClick={isMyTurn ? onRotate : undefined}
          onDoubleClick={isMyTurn ? onFlip : undefined}
          title={isMyTurn ? t('game.clickRotate', 'Click to rotate, double-click to flip') : ''}
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
