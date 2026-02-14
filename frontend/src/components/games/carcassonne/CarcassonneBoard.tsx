'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { CarcassonneGameData, TilePlacement, Player } from '@/lib/types';
import { preloadTileImages } from '@/lib/tileImages';
import { MeepleSpotInfo } from '@/lib/meeplePlacements';

interface CarcassonneBoardProps {
  gameData: CarcassonneGameData;
  players: Player[];
  validCells: { x: number; y: number }[];
  selectedCell: { x: number; y: number } | null;
  currentPreview: TilePlacement | null;
  onCellClicked: (x: number, y: number) => void;
  isMyTurn: boolean;
  phase: string;
  // Tile confirm
  showConfirmButton: boolean;
  onConfirmTile: () => void;
  // Meeple placement overlay
  meeplePlacementMode: boolean;
  meepleSpots: MeepleSpotInfo[];
  selectedMeepleSpot: string | null;
  onMeepleSpotClick: (spot: string) => void;
  onConfirmMeeple: () => void;
  onSkipMeeple: () => void;
  lastPlacedPosition: { x: number; y: number } | null;
  playerMeepleImage: string;
  playerSeatIndex: number;
  // Confirmed tile to draw during meeple placement (before server has it on the board)
  confirmedTile: { tileType: string; x: number; y: number; rotation: number } | null;
}

const TILE_SIZE = 100;
const PLAYER_COLORS = ['#ef4444', '#3b82f6', '#22c55e', '#eab308', '#a855f7'];

interface Camera {
  x: number;
  y: number;
  zoom: number;
}

export default function CarcassonneBoard({
  gameData,
  players,
  validCells,
  selectedCell,
  currentPreview,
  onCellClicked,
  isMyTurn,
  phase,
  showConfirmButton,
  onConfirmTile,
  meeplePlacementMode,
  meepleSpots,
  selectedMeepleSpot,
  onMeepleSpotClick,
  onConfirmMeeple,
  onSkipMeeple,
  lastPlacedPosition,
  playerMeepleImage,
  playerSeatIndex,
  confirmedTile,
}: CarcassonneBoardProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [tileImages, setTileImages] = useState<Map<string, HTMLImageElement> | null>(null);
  const [camera, setCamera] = useState<Camera>({ x: 0, y: 0, zoom: 1 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  // Track canvas dimensions in state so render effect re-fires when they change
  const [canvasDims, setCanvasDims] = useState({ width: 0, height: 0 });

  // Load tile images
  useEffect(() => {
    preloadTileImages().then(setTileImages);
  }, []);

  // Resize observer for responsive canvas — updates canvasDims state
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

  // Native wheel handler to reliably prevent default browser behavior
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setCamera((prev) => ({
        ...prev,
        zoom: Math.max(0.25, Math.min(4.0, prev.zoom - e.deltaY * 0.001)),
      }));
    };

    canvas.addEventListener('wheel', handleWheel, { passive: false });
    return () => canvas.removeEventListener('wheel', handleWheel);
  }, []);

  // Convert screen coordinates to grid coordinates — fixed Y-axis
  const screenToGrid = useCallback(
    (screenX: number, screenY: number): { x: number; y: number } => {
      const canvas = canvasRef.current;
      if (!canvas) return { x: 0, y: 0 };

      const rect = canvas.getBoundingClientRect();
      const canvasX = screenX - rect.left;
      const canvasY = screenY - rect.top;

      const worldX = (canvasX - canvas.width / 2 - camera.x) / (TILE_SIZE * camera.zoom);
      // Negate AFTER floor, not before — fixes off-by-one on Y axis
      const rawWorldY = (canvasY - canvas.height / 2 - camera.y) / (TILE_SIZE * camera.zoom);

      return {
        x: Math.floor(worldX),
        y: -Math.floor(rawWorldY),
      };
    },
    [camera]
  );

  // Convert grid coordinates to screen pixel position (for DOM overlay)
  const gridToScreen = useCallback(
    (gridX: number, gridY: number): { x: number; y: number } => {
      const canvas = canvasRef.current;
      if (!canvas) return { x: 0, y: 0 };

      const screenX = (gridX * TILE_SIZE) * camera.zoom + canvas.width / 2 + camera.x;
      const screenY = (-gridY * TILE_SIZE) * camera.zoom + canvas.height / 2 + camera.y;

      return { x: screenX, y: screenY };
    },
    [camera]
  );

  // Mouse down - start panning
  const handleMouseDown = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      setIsDragging(true);
      setDragStart({ x: e.clientX - camera.x, y: e.clientY - camera.y });
    },
    [camera]
  );

  // Mouse move - pan
  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (isDragging) {
        setCamera((prev) => ({
          ...prev,
          x: e.clientX - dragStart.x,
          y: e.clientY - dragStart.y,
        }));
      }
    },
    [isDragging, dragStart]
  );

  // Mouse up - click to select cell or stop panning
  const handleMouseUp = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (isDragging) {
        const dragDistance = Math.sqrt(
          Math.pow(e.clientX - (dragStart.x + camera.x), 2) +
            Math.pow(e.clientY - (dragStart.y + camera.y), 2)
        );

        if (dragDistance < 5 && isMyTurn && phase === 'place_tile') {
          const gridPos = screenToGrid(e.clientX, e.clientY);
          onCellClicked(gridPos.x, gridPos.y);
        }
      }
      setIsDragging(false);
    },
    [isDragging, dragStart, camera, isMyTurn, phase, screenToGrid, onCellClicked]
  );

  // Render canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx || !tileImages) return;
    if (canvasDims.width === 0 || canvasDims.height === 0) return;

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Save context and apply camera transform
    ctx.save();
    ctx.translate(canvas.width / 2 + camera.x, canvas.height / 2 + camera.y);
    ctx.scale(camera.zoom, camera.zoom);

    // Draw grid (subtle)
    ctx.strokeStyle = '#e5e7eb';
    ctx.lineWidth = 1 / camera.zoom;

    // Calculate visible grid range
    const minX = Math.floor((-canvas.width / 2 - camera.x) / (TILE_SIZE * camera.zoom)) - 1;
    const maxX = Math.ceil((canvas.width / 2 - camera.x) / (TILE_SIZE * camera.zoom)) + 1;
    const minY = Math.floor((-canvas.height / 2 - camera.y) / (TILE_SIZE * camera.zoom)) - 1;
    const maxY = Math.ceil((canvas.height / 2 - camera.y) / (TILE_SIZE * camera.zoom)) + 1;

    for (let x = minX; x <= maxX; x++) {
      ctx.beginPath();
      ctx.moveTo(x * TILE_SIZE, minY * TILE_SIZE);
      ctx.lineTo(x * TILE_SIZE, maxY * TILE_SIZE);
      ctx.stroke();
    }
    for (let y = minY; y <= maxY; y++) {
      ctx.beginPath();
      ctx.moveTo(minX * TILE_SIZE, -y * TILE_SIZE);
      ctx.lineTo(maxX * TILE_SIZE, -y * TILE_SIZE);
      ctx.stroke();
    }

    // Draw placed tiles
    Object.entries(gameData.board.tiles).forEach(([posKey, tile]) => {
      const [x, y] = posKey.split(',').map(Number);
      const tileImage = tileImages.get(tile.tile_type_id);
      if (!tileImage) return;

      const drawX = x * TILE_SIZE;
      const drawY = -y * TILE_SIZE;

      ctx.save();
      ctx.translate(drawX + TILE_SIZE / 2, drawY + TILE_SIZE / 2);
      ctx.rotate((tile.rotation * Math.PI) / 180);
      ctx.drawImage(tileImage, -TILE_SIZE / 2, -TILE_SIZE / 2, TILE_SIZE, TILE_SIZE);
      ctx.restore();
    });

    // Draw meeples
    if (gameData.features) {
      Object.values(gameData.features).forEach((feature) => {
        if (feature.meeples && feature.meeples.length > 0) {
          feature.meeples.forEach((meeple) => {
            const [x, y] = meeple.position.split(',').map(Number);

            const playerSeat = players.find(
              (p) => p.player_id === meeple.player_id
            )?.seat_index || 0;
            const playerColor = PLAYER_COLORS[playerSeat % PLAYER_COLORS.length];

            let offsetX = 0;
            let offsetY = 0;

            if (meeple.spot.includes('N')) offsetY = -TILE_SIZE / 4;
            if (meeple.spot.includes('S')) offsetY = TILE_SIZE / 4;
            if (meeple.spot.includes('E')) offsetX = TILE_SIZE / 4;
            if (meeple.spot.includes('W')) offsetX = -TILE_SIZE / 4;

            const meepleX = x * TILE_SIZE + TILE_SIZE / 2 + offsetX;
            const meepleY = -y * TILE_SIZE + TILE_SIZE / 2 + offsetY;

            ctx.fillStyle = playerColor;
            ctx.strokeStyle = '#000';
            ctx.lineWidth = 2 / camera.zoom;
            ctx.beginPath();
            ctx.arc(meepleX, meepleY, 12, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
          });
        }
      });
    }

    // Draw valid cell highlights (all positions, any rotation)
    if (isMyTurn && phase === 'place_tile' && !meeplePlacementMode) {
      validCells.forEach((cell) => {
        const drawX = cell.x * TILE_SIZE;
        const drawY = -cell.y * TILE_SIZE;

        ctx.fillStyle = 'rgba(34, 197, 94, 0.3)';
        ctx.fillRect(drawX, drawY, TILE_SIZE, TILE_SIZE);
        ctx.strokeStyle = '#22c55e';
        ctx.lineWidth = 2 / camera.zoom;
        ctx.strokeRect(drawX, drawY, TILE_SIZE, TILE_SIZE);
      });
    }

    // Draw selected cell highlight
    if (selectedCell && !meeplePlacementMode) {
      const drawX = selectedCell.x * TILE_SIZE;
      const drawY = -selectedCell.y * TILE_SIZE;
      ctx.strokeStyle = '#3b82f6';
      ctx.lineWidth = 4 / camera.zoom;
      ctx.strokeRect(drawX, drawY, TILE_SIZE, TILE_SIZE);
    }

    // Draw tile preview at selected cell (during tile selection phase)
    if (currentPreview && gameData.current_tile && !meeplePlacementMode) {
      const tileImage = tileImages.get(gameData.current_tile);
      if (tileImage) {
        const drawX = currentPreview.x * TILE_SIZE;
        const drawY = -currentPreview.y * TILE_SIZE;

        ctx.save();
        ctx.globalAlpha = 0.7;
        ctx.translate(drawX + TILE_SIZE / 2, drawY + TILE_SIZE / 2);
        ctx.rotate((currentPreview.rotation * Math.PI) / 180);
        ctx.drawImage(tileImage, -TILE_SIZE / 2, -TILE_SIZE / 2, TILE_SIZE, TILE_SIZE);
        ctx.restore();
      }
    }

    // Draw confirmed tile during meeple placement (tile not yet on server board)
    if (confirmedTile && meeplePlacementMode) {
      const tileImage = tileImages.get(confirmedTile.tileType);
      if (tileImage) {
        const drawX = confirmedTile.x * TILE_SIZE;
        const drawY = -confirmedTile.y * TILE_SIZE;

        ctx.save();
        ctx.translate(drawX + TILE_SIZE / 2, drawY + TILE_SIZE / 2);
        ctx.rotate((confirmedTile.rotation * Math.PI) / 180);
        ctx.drawImage(tileImage, -TILE_SIZE / 2, -TILE_SIZE / 2, TILE_SIZE, TILE_SIZE);
        ctx.restore();
      }
    }

    ctx.restore();
  }, [
    camera,
    canvasDims,
    tileImages,
    gameData,
    players,
    validCells,
    selectedCell,
    currentPreview,
    isMyTurn,
    phase,
    meeplePlacementMode,
    confirmedTile,
  ]);

  // Compute overlay positions for buttons and meeple spots
  const overlayTilePos = meeplePlacementMode && lastPlacedPosition
    ? lastPlacedPosition
    : (showConfirmButton && selectedCell ? selectedCell : null);

  const tileScreenPos = overlayTilePos ? gridToScreen(overlayTilePos.x, overlayTilePos.y) : null;
  const tileSizePx = TILE_SIZE * camera.zoom;

  return (
    <div ref={containerRef} className="w-full h-full bg-gray-100 relative overflow-hidden">
      <canvas
        ref={canvasRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={() => {
          setIsDragging(false);
        }}
        className="w-full h-full cursor-grab active:cursor-grabbing"
      />

      {/* DOM Overlay: Confirm/Skip buttons and meeple spots */}
      {tileScreenPos && (
        <div
          style={{
            position: 'absolute',
            left: tileScreenPos.x,
            top: tileScreenPos.y,
            width: tileSizePx,
            height: tileSizePx,
            pointerEvents: 'none',
          }}
        >
          {/* Confirm button (top-right of tile) */}
          {showConfirmButton && !meeplePlacementMode && (
            <button
              onClick={(e) => { e.stopPropagation(); onConfirmTile(); }}
              style={{
                position: 'absolute',
                top: -20,
                right: -20,
                width: 40,
                height: 40,
                pointerEvents: 'auto',
                cursor: 'pointer',
                border: 'none',
                background: 'none',
                padding: 0,
              }}
              title="Confirm tile placement"
            >
              <img src="/icon-accept-48.png" alt="Confirm" style={{ width: '100%', height: '100%' }} />
            </button>
          )}

          {/* Meeple placement mode: spots + confirm/skip */}
          {meeplePlacementMode && (
            <>
              {/* Meeple spot indicators */}
              {meepleSpots.map((spotInfo) => {
                const isSelected = selectedMeepleSpot === spotInfo.spot;
                // Convert from 100x100 space to actual pixel space
                const spotX = (spotInfo.column / 100) * tileSizePx + tileSizePx / 2;
                const spotY = (spotInfo.row / 100) * tileSizePx + tileSizePx / 2;
                const spotSize = Math.max(20, tileSizePx * 0.22);

                return (
                  <button
                    key={spotInfo.spot}
                    onClick={(e) => { e.stopPropagation(); onMeepleSpotClick(spotInfo.spot); }}
                    style={{
                      position: 'absolute',
                      left: spotX - spotSize / 2,
                      top: spotY - spotSize / 2,
                      width: spotSize,
                      height: spotSize,
                      pointerEvents: 'auto',
                      cursor: 'pointer',
                      border: isSelected ? `2px solid ${PLAYER_COLORS[playerSeatIndex % PLAYER_COLORS.length]}` : 'none',
                      borderRadius: '50%',
                      background: 'none',
                      padding: 0,
                      zIndex: isSelected ? 10 : 1,
                    }}
                    title={spotInfo.spot}
                  >
                    <img
                      src={isSelected ? playerMeepleImage : '/spot.gif'}
                      alt={spotInfo.spot}
                      style={{ width: '100%', height: '100%', borderRadius: '50%' }}
                    />
                  </button>
                );
              })}

              {/* Confirm meeple button */}
              <button
                onClick={(e) => { e.stopPropagation(); onConfirmMeeple(); }}
                style={{
                  position: 'absolute',
                  top: -20,
                  right: -20,
                  width: 40,
                  height: 40,
                  pointerEvents: 'auto',
                  cursor: 'pointer',
                  border: 'none',
                  background: 'none',
                  padding: 0,
                }}
                title="Confirm meeple placement"
              >
                <img src="/icon-accept-48.png" alt="Confirm" style={{ width: '100%', height: '100%' }} />
              </button>

              {/* Skip meeple button */}
              <button
                onClick={(e) => { e.stopPropagation(); onSkipMeeple(); }}
                style={{
                  position: 'absolute',
                  top: -20,
                  right: -64,
                  width: 40,
                  height: 40,
                  pointerEvents: 'auto',
                  cursor: 'pointer',
                  border: 'none',
                  background: 'none',
                  padding: 0,
                }}
                title="Skip meeple"
              >
                <img src="/icon-reject-48.png" alt="Skip" style={{ width: '100%', height: '100%' }} />
              </button>
            </>
          )}
        </div>
      )}

      <div className="absolute bottom-4 left-4 bg-white px-3 py-2 rounded shadow text-sm">
        <div>Zoom: {(camera.zoom * 100).toFixed(0)}%</div>
        <div className="text-xs text-gray-500">Scroll to zoom, drag to pan</div>
      </div>
    </div>
  );
}
