'use client';

import { useState, useMemo, useEffect, useCallback } from 'react';
import { PlayerView, CarcassonneGameData, TilePlacement, ValidAction, isTilePlacementAction, isMeeplePlacementAction, isSkipAction } from '@/lib/types';
import CarcassonneBoard from './CarcassonneBoard';
import TilePreview from './TilePreview';
import MeeplePlacementPanel from './MeeplePlacement';
import MeepleSupply from './MeepleSupply';
import ScoreBoard from '../../game/ScoreBoard';

interface CarcassonneRendererProps {
  view: PlayerView;
  onAction: (actionType: string, payload: Record<string, unknown>) => void;
  isMyTurn: boolean;
  phase: string;
}

export default function CarcassonneRenderer({
  view,
  onAction,
  isMyTurn,
  phase,
}: CarcassonneRendererProps) {
  // Local state for the combined tile+meeple flow
  const [selectedCell, setSelectedCell] = useState<{ x: number; y: number } | null>(null);
  const [rotationIndex, setRotationIndex] = useState(0);
  // undefined = no pending, null = skip/no meeple, string = meeple spot
  const [pendingMeepleAction, setPendingMeepleAction] = useState<string | null | undefined>(undefined);

  // Extract game data
  const gameData = view.game_data as CarcassonneGameData;

  // Determine whose turn it is
  const currentAction = view.current_phase?.expected_actions?.[0];
  const currentPlayerId = currentAction?.player_id;

  // All valid tile placements (enriched with meeple_spots)
  const validTilePlacements = useMemo(() => {
    if (phase !== 'place_tile' || !view.valid_actions) {
      return [];
    }
    return view.valid_actions.filter(isTilePlacementAction) as TilePlacement[];
  }, [phase, view.valid_actions]);

  // Server-validated meeple placements (for fallback mode)
  const validMeeplePlacements = useMemo(() => {
    if (phase !== 'place_meeple' || !view.valid_actions) {
      return [];
    }
    return view.valid_actions.filter(
      (action: ValidAction) => isMeeplePlacementAction(action) || isSkipAction(action)
    );
  }, [phase, view.valid_actions]);

  // Deduplicated valid cells (positions where tile can go in ANY rotation)
  const validCells = useMemo(() => {
    const cellSet = new Map<string, { x: number; y: number }>();
    for (const action of validTilePlacements) {
      const key = `${action.x},${action.y}`;
      if (!cellSet.has(key)) {
        cellSet.set(key, { x: action.x, y: action.y });
      }
    }
    return Array.from(cellSet.values());
  }, [validTilePlacements]);

  // Valid rotations for the selected cell
  const validRotationsForCell = useMemo(() => {
    if (!selectedCell) return [];
    return validTilePlacements
      .filter(a => a.x === selectedCell.x && a.y === selectedCell.y)
      .sort((a, b) => a.rotation - b.rotation);
  }, [validTilePlacements, selectedCell]);

  // Current preview placement
  const currentPreview = validRotationsForCell[rotationIndex] || null;

  // Meeple spots for current preview
  const previewMeepleSpots = currentPreview?.meeple_spots || [];

  // Reset local state on turn change
  useEffect(() => {
    setSelectedCell(null);
    setRotationIndex(0);
    setPendingMeepleAction(undefined);
  }, [view.turn_number]);

  // Auto-send place_meeple when phase transitions after our place_tile
  useEffect(() => {
    if (phase !== 'place_meeple' || pendingMeepleAction === undefined) return;

    if (pendingMeepleAction === null) {
      // User chose "No Meeple"
      onAction('place_meeple', { skip: true });
    } else {
      // User chose a specific spot — verify it's still valid after server processing
      const spotStillValid = validMeeplePlacements.some(
        a => 'meeple_spot' in a && (a as { meeple_spot: string }).meeple_spot === pendingMeepleAction
      );
      if (spotStillValid) {
        onAction('place_meeple', { meeple_spot: pendingMeepleAction });
      } else {
        // Spot invalidated by feature merge — show fallback meeple panel
        setPendingMeepleAction(undefined);
        return; // Don't clear selection yet — user needs to pick again
      }
    }

    // Clear state after sending
    setPendingMeepleAction(undefined);
    setSelectedCell(null);
    setRotationIndex(0);
  }, [phase, pendingMeepleAction, validMeeplePlacements, onAction]);

  // Board click handler
  const handleBoardClick = useCallback((x: number, y: number) => {
    const isValidCell = validCells.some(c => c.x === x && c.y === y);

    if (!isValidCell) {
      setSelectedCell(null);
      setRotationIndex(0);
      return;
    }

    if (selectedCell && selectedCell.x === x && selectedCell.y === y) {
      // Same cell — cycle rotation
      setRotationIndex((prev) => (prev + 1) % validRotationsForCell.length);
    } else {
      // Different valid cell — select it
      setSelectedCell({ x, y });
      setRotationIndex(0);
    }
  }, [validCells, selectedCell, validRotationsForCell.length]);

  // Confirm placement: sends place_tile, buffers meeple action
  const handleConfirmPlacement = useCallback((meepleSpot: string | null) => {
    if (!currentPreview) return;

    setPendingMeepleAction(meepleSpot);
    onAction('place_tile', {
      x: currentPreview.x,
      y: currentPreview.y,
      rotation: currentPreview.rotation,
    });
  }, [currentPreview, onAction]);

  // Fallback meeple handlers (when server shows real meeple phase)
  const handleMeeplePlaced = useCallback((spot: string) => {
    onAction('place_meeple', { meeple_spot: spot });
  }, [onAction]);

  const handleMeepleSkip = useCallback(() => {
    onAction('place_meeple', { skip: true });
  }, [onAction]);

  // Prepare scores
  const scores = useMemo(() => {
    const scoreMap: Record<string, number> = {};
    view.players.forEach(player => {
      scoreMap[player.player_id] = gameData.scores?.[player.player_id] || 0;
    });
    return scoreMap;
  }, [view.players, gameData.scores]);

  // Determine which rotation to show in the TilePreview sidebar
  const previewRotation = currentPreview?.rotation ?? 0;

  // Should we show the fallback meeple panel? (place_meeple phase with no pending action)
  const showFallbackMeeple = phase === 'place_meeple' && pendingMeepleAction === undefined;

  // Should we show the preview meeple panel? (place_tile phase with a cell selected)
  const showPreviewMeeple = phase === 'place_tile' && selectedCell !== null && currentPreview !== null && isMyTurn;

  return (
    <div className="flex h-full">
      {/* Board area */}
      <div className="flex-1 relative">
        <CarcassonneBoard
          gameData={gameData}
          players={view.players}
          validCells={validCells}
          selectedCell={selectedCell}
          currentPreview={currentPreview}
          onCellClicked={handleBoardClick}
          isMyTurn={isMyTurn}
          phase={phase}
        />
      </div>

      {/* Sidebar */}
      <div className="w-80 border-l bg-gray-50 p-4 flex flex-col gap-4 overflow-y-auto">
        {/* Tile Preview */}
        <TilePreview
          currentTile={gameData.current_tile}
          selectedRotation={previewRotation}
          isMyTurn={isMyTurn}
          phase={phase}
          hasSelection={selectedCell !== null}
        />

        {/* Meeple Placement — preview mode (during place_tile with selection) */}
        {showPreviewMeeple && (
          <MeeplePlacementPanel
            meepleSpots={previewMeepleSpots}
            onMeeplePlaced={(spot) => handleConfirmPlacement(spot)}
            onSkip={() => handleConfirmPlacement(null)}
            isMyTurn={isMyTurn}
            isPreview={true}
          />
        )}

        {/* Meeple Placement — fallback mode (during place_meeple phase) */}
        {showFallbackMeeple && (
          <MeeplePlacementPanel
            validActions={validMeeplePlacements}
            onMeeplePlaced={handleMeeplePlaced}
            onSkip={handleMeepleSkip}
            isMyTurn={isMyTurn}
          />
        )}

        {/* Meeple Supply */}
        <MeepleSupply
          meepleSupply={gameData.meeple_supply || {}}
          players={view.players}
        />

        {/* Score Board */}
        <ScoreBoard
          players={view.players}
          scores={scores}
          currentPlayerId={currentPlayerId ?? undefined}
          viewerId={view.viewer_id ?? undefined}
        />

        {/* Tiles Remaining */}
        <div className="bg-white rounded-lg border shadow-sm px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-600">Tiles remaining:</span>
            <span className="text-lg font-bold">{gameData.tiles_remaining || 0}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
