'use client';

import { useEffect, useRef, useState } from 'react';
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
    if (!currentTile) return 'Drawing tile...';
    if (!isMyTurn) return 'Waiting for opponent...';
    if (phase === 'place_tile') {
      if (hasSelection) return 'Click cell to rotate. Choose meeple to confirm.';
      return 'Click a highlighted cell to place';
    }
    if (phase === 'place_meeple') return 'Choose a meeple placement';
    return '';
  };

  return (
    <div className="bg-white rounded-lg border shadow-sm">
      <div className="px-4 py-2 border-b font-semibold">Current Tile</div>
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
              <span className="text-gray-400 text-sm">No tile</span>
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
