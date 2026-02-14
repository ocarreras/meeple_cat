'use client';

import { useEffect, useRef, useState } from 'react';
import { preloadTileImages } from '@/lib/tileImages';

interface TilePreviewProps {
  currentTile: string | null;
  selectedRotation: number;
  onRotationChange: (rotation: number) => void;
  isMyTurn: boolean;
  phase: string;
}

export default function TilePreview({
  currentTile,
  selectedRotation,
  onRotationChange,
  isMyTurn,
  phase,
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

  const handleRotateLeft = () => {
    const rotations = [0, 90, 180, 270];
    const currentIndex = rotations.indexOf(selectedRotation);
    const newIndex = (currentIndex - 1 + rotations.length) % rotations.length;
    onRotationChange(rotations[newIndex]);
  };

  const handleRotateRight = () => {
    const rotations = [0, 90, 180, 270];
    const currentIndex = rotations.indexOf(selectedRotation);
    const newIndex = (currentIndex + 1) % rotations.length;
    onRotationChange(rotations[newIndex]);
  };

  const getStatusText = () => {
    if (!currentTile) return 'Drawing tile...';
    if (!isMyTurn) return 'Waiting for opponent...';
    if (phase === 'place_tile') return 'Place this tile';
    if (phase === 'place_meeple') return 'Place a meeple or skip';
    return '';
  };

  return (
    <div className="bg-white rounded-lg border shadow-sm">
      <div className="px-4 py-2 border-b font-semibold">Current Tile</div>
      <div className="p-4">
        <div className="flex flex-col items-center gap-3">
          {currentTile ? (
            <>
              <canvas
                ref={canvasRef}
                width={120}
                height={120}
                className="border rounded"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleRotateLeft}
                  disabled={!isMyTurn || phase !== 'place_tile'}
                  className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
                  title="Rotate counterclockwise"
                >
                  ←
                </button>
                <button
                  onClick={handleRotateRight}
                  disabled={!isMyTurn || phase !== 'place_tile'}
                  className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
                  title="Rotate clockwise"
                >
                  →
                </button>
              </div>
            </>
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
