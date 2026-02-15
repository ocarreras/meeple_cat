'use client';

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { preloadTileImages } from '@/lib/tileImages';

interface TilePreviewProps {
  currentTile: string | null;
  selectedRotation: number;
  isMyTurn: boolean;
  phase: string;
  hasSelection: boolean;
}

export default function TilePreview({
  currentTile,
  selectedRotation,
  isMyTurn,
  phase,
  hasSelection,
}: TilePreviewProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { t } = useTranslation();
  const [tileImages, setTileImages] = useState<Map<string, HTMLImageElement> | null>(null);

  useEffect(() => {
    preloadTileImages().then(setTileImages);
  }, []);

  useEffect(() => {
    if (!canvasRef.current || !tileImages || !currentTile) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const tileImage = tileImages.get(currentTile);
    if (!tileImage) return;

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw tile with rotation
    ctx.save();
    ctx.translate(canvas.width / 2, canvas.height / 2);
    ctx.rotate((selectedRotation * Math.PI) / 180);
    ctx.drawImage(tileImage, -canvas.width / 2, -canvas.height / 2, canvas.width, canvas.height);
    ctx.restore();
  }, [currentTile, selectedRotation, tileImages]);

  const getStatusText = () => {
    if (!currentTile) return t('game.status.drawingTile');
    if (!isMyTurn) return t('game.status.waitingOpponent');
    if (phase === 'place_tile') {
      if (hasSelection) return t('game.status.clickToRotate');
      return t('game.status.clickToPlace');
    }
    if (phase === 'confirming_meeple') return t('game.status.selectMeeple');
    if (phase === 'waiting') return t('game.status.waitingServer');
    if (phase === 'place_meeple') return t('game.status.selectMeeple');
    return '';
  };

  return (
    <div className="bg-white rounded-lg border shadow-sm">
      <div className="px-4 py-2 border-b font-semibold">{t('game.currentTile')}</div>
      <div className="p-4">
        <div className="flex flex-col items-center gap-3">
          {currentTile ? (
            <canvas
              ref={canvasRef}
              width={120}
              height={120}
              className="border rounded"
            />
          ) : (
            <div className="w-[120px] h-[120px] border rounded bg-gray-100 flex items-center justify-center">
              <span className="text-gray-400 text-sm">{t('game.noTile')}</span>
            </div>
          )}
          <p className="text-sm text-center text-gray-600 font-medium">
            {getStatusText()}
          </p>
        </div>
      </div>
    </div>
  );
}
