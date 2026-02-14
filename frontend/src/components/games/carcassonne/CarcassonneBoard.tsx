'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { CarcassonneGameData, TilePlacement, Player } from '@/lib/types';
import { preloadTileImages } from '@/lib/tileImages';

interface CarcassonneBoardProps {
  gameData: CarcassonneGameData;
  players: Player[];
  validActions: TilePlacement[];
  onTilePlaced: (x: number, y: number, rotation: number) => void;
  selectedRotation: number;
  isMyTurn: boolean;
  phase: string;
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
  validActions,
  onTilePlaced,
  selectedRotation,
  isMyTurn,
  phase,
}: CarcassonneBoardProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [tileImages, setTileImages] = useState<Map<string, HTMLImageElement> | null>(null);
  const [camera, setCamera] = useState<Camera>({ x: 0, y: 0, zoom: 1 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [hoveredCell, setHoveredCell] = useState<{ x: number; y: number } | null>(null);
  const [lastPlacedTile, setLastPlacedTile] = useState<{ x: number; y: number } | null>(null);

  // Load tile images
  useEffect(() => {
    preloadTileImages().then(setTileImages);
  }, []);

  // Track last placed tile
  useEffect(() => {
    const positions = Object.keys(gameData.board.tiles);
    if (positions.length > 0) {
      const lastPos = positions[positions.length - 1];
      const [x, y] = lastPos.split(',').map(Number);
      setLastPlacedTile({ x, y });
    }
  }, [gameData.board.tiles]);

  // Resize observer for responsive canvas
  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        canvas.width = width;
        canvas.height = height;
      }
    });

    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, []);

  // Convert screen coordinates to grid coordinates
  const screenToGrid = useCallback(
    (screenX: number, screenY: number): { x: number; y: number } => {
      const canvas = canvasRef.current;
      if (!canvas) return { x: 0, y: 0 };

      const rect = canvas.getBoundingClientRect();
      const canvasX = screenX - rect.left;
      const canvasY = screenY - rect.top;

      const worldX = (canvasX - canvas.width / 2 - camera.x) / (TILE_SIZE * camera.zoom);
      const worldY = -(canvasY - canvas.height / 2 - camera.y) / (TILE_SIZE * camera.zoom);

      return {
        x: Math.floor(worldX),
        y: Math.floor(worldY),
      };
    },
    [camera]
  );

  // Mouse wheel zoom
  const handleWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    setCamera((prev) => ({
      ...prev,
      zoom: Math.max(0.25, Math.min(4.0, prev.zoom - e.deltaY * 0.001)),
    }));
  }, []);

  // Mouse down - start panning
  const handleMouseDown = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      setIsDragging(true);
      setDragStart({ x: e.clientX - camera.x, y: e.clientY - camera.y });
    },
    [camera]
  );

  // Mouse move - pan or hover
  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (isDragging) {
        setCamera((prev) => ({
          ...prev,
          x: e.clientX - dragStart.x,
          y: e.clientY - dragStart.y,
        }));
      } else if (isMyTurn && phase === 'place_tile') {
        const gridPos = screenToGrid(e.clientX, e.clientY);
        const validPlacements = validActions.filter(
          (action) => action.rotation === selectedRotation
        );
        const isValid = validPlacements.some(
          (action) => action.x === gridPos.x && action.y === gridPos.y
        );
        setHoveredCell(isValid ? gridPos : null);
      } else {
        setHoveredCell(null);
      }
    },
    [isDragging, dragStart, isMyTurn, phase, screenToGrid, validActions, selectedRotation]
  );

  // Mouse up - place tile or stop panning
  const handleMouseUp = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (isDragging) {
        const dragDistance = Math.sqrt(
          Math.pow(e.clientX - (dragStart.x + camera.x), 2) +
            Math.pow(e.clientY - (dragStart.y + camera.y), 2)
        );

        if (dragDistance < 5 && isMyTurn && phase === 'place_tile') {
          const gridPos = screenToGrid(e.clientX, e.clientY);
          const validPlacements = validActions.filter(
            (action) => action.rotation === selectedRotation
          );
          const isValid = validPlacements.some(
            (action) => action.x === gridPos.x && action.y === gridPos.y
          );

          if (isValid) {
            onTilePlaced(gridPos.x, gridPos.y, selectedRotation);
          }
        }
      }
      setIsDragging(false);
    },
    [isDragging, dragStart, camera, isMyTurn, phase, screenToGrid, validActions, selectedRotation, onTilePlaced]
  );

  // Render canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx || !tileImages) return;

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

      // Highlight last placed tile
      if (lastPlacedTile && lastPlacedTile.x === x && lastPlacedTile.y === y) {
        ctx.strokeStyle = '#fbbf24';
        ctx.lineWidth = 4 / camera.zoom;
        ctx.strokeRect(drawX, drawY, TILE_SIZE, TILE_SIZE);
      }
    });

    // Draw meeples
    if (gameData.features) {
      Object.values(gameData.features).forEach((feature) => {
        if (feature.meeples && feature.meeples.length > 0) {
          feature.meeples.forEach((meeple) => {
            const [x, y] = meeple.position.split(',').map(Number);

            // Find player seat for color
            const playerSeat = players.find(
              (p) => p.player_id === meeple.player_id
            )?.seat_index || 0;
            const playerColor = PLAYER_COLORS[playerSeat % PLAYER_COLORS.length];

            // Calculate meeple position (center of tile with slight offset)
            let offsetX = 0;
            let offsetY = 0;

            // Parse spot for directional offset
            if (meeple.spot.includes('N')) offsetY = -TILE_SIZE / 4;
            if (meeple.spot.includes('S')) offsetY = TILE_SIZE / 4;
            if (meeple.spot.includes('E')) offsetX = TILE_SIZE / 4;
            if (meeple.spot.includes('W')) offsetX = -TILE_SIZE / 4;

            const meepleX = x * TILE_SIZE + TILE_SIZE / 2 + offsetX;
            const meepleY = -y * TILE_SIZE + TILE_SIZE / 2 + offsetY;

            // Draw meeple as a circle
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

    // Draw valid placements
    if (isMyTurn && phase === 'place_tile' && gameData.current_tile) {
      const validPlacements = validActions.filter(
        (action) => action.rotation === selectedRotation
      );

      validPlacements.forEach((action) => {
        const drawX = action.x * TILE_SIZE;
        const drawY = -action.y * TILE_SIZE;

        ctx.fillStyle = 'rgba(34, 197, 94, 0.3)';
        ctx.fillRect(drawX, drawY, TILE_SIZE, TILE_SIZE);
        ctx.strokeStyle = '#22c55e';
        ctx.lineWidth = 2 / camera.zoom;
        ctx.strokeRect(drawX, drawY, TILE_SIZE, TILE_SIZE);
      });
    }

    // Draw hovered tile preview
    if (hoveredCell && gameData.current_tile) {
      const tileImage = tileImages.get(gameData.current_tile);
      if (tileImage) {
        const drawX = hoveredCell.x * TILE_SIZE;
        const drawY = -hoveredCell.y * TILE_SIZE;

        ctx.save();
        ctx.globalAlpha = 0.6;
        ctx.translate(drawX + TILE_SIZE / 2, drawY + TILE_SIZE / 2);
        ctx.rotate((selectedRotation * Math.PI) / 180);
        ctx.drawImage(tileImage, -TILE_SIZE / 2, -TILE_SIZE / 2, TILE_SIZE, TILE_SIZE);
        ctx.restore();
      }
    }

    ctx.restore();
  }, [
    camera,
    tileImages,
    gameData,
    players,
    validActions,
    selectedRotation,
    isMyTurn,
    phase,
    hoveredCell,
    lastPlacedTile,
  ]);

  return (
    <div ref={containerRef} className="w-full h-full bg-gray-100">
      <canvas
        ref={canvasRef}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={() => {
          setIsDragging(false);
          setHoveredCell(null);
        }}
        className="w-full h-full cursor-grab active:cursor-grabbing"
      />
      <div className="absolute bottom-4 left-4 bg-white px-3 py-2 rounded shadow text-sm">
        <div>Zoom: {(camera.zoom * 100).toFixed(0)}%</div>
        <div className="text-xs text-gray-500">Scroll to zoom, drag to pan</div>
      </div>
    </div>
  );
}
