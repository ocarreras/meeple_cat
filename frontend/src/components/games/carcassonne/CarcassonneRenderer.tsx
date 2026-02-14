'use client';

import { useState, useMemo, useEffect, useCallback } from 'react';
import { PlayerView, CarcassonneGameData, TilePlacement, ValidAction, isTilePlacementAction, isMeeplePlacementAction, isSkipAction } from '@/lib/types';
import { getValidMeepleSpots, MeepleSpotInfo } from '@/lib/meeplePlacements';
import CarcassonneBoard from './CarcassonneBoard';
import TilePreview from './TilePreview';
import MeepleSupply from './MeepleSupply';
import ScoreBoard from '../../game/ScoreBoard';

type UIPhase = 'selecting_tile' | 'confirming_meeple' | 'waiting';

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
  const [selectedCell, setSelectedCell] = useState<{ x: number; y: number } | null>(null);
  const [rotationIndex, setRotationIndex] = useState(0);
  const [uiPhase, setUiPhase] = useState<UIPhase>('selecting_tile');
  const [selectedMeepleSpot, setSelectedMeepleSpot] = useState<string | null>(null);
  // Buffered meeple action: undefined = no pending, null = skip, string = spot
  const [bufferedMeeple, setBufferedMeeple] = useState<string | null | undefined>(undefined);
  // Track the tile placement that was confirmed (for meeple overlay positioning)
  const [confirmedPlacement, setConfirmedPlacement] = useState<TilePlacement | null>(null);

  const gameData = view.game_data as CarcassonneGameData;

  const currentAction = view.current_phase?.expected_actions?.[0];
  const currentPlayerId = currentAction?.player_id;

  // Viewer's seat index and meeple image
  const viewerPlayer = view.players.find(p => p.player_id === view.viewer_id);
  const playerSeatIndex = viewerPlayer?.seat_index ?? 0;
  const playerMeepleImage = `/meeples/${playerSeatIndex}.png`;

  // All valid tile placements
  const validTilePlacements = useMemo(() => {
    if (phase !== 'place_tile' || !view.valid_actions) return [];
    return view.valid_actions.filter(isTilePlacementAction) as TilePlacement[];
  }, [phase, view.valid_actions]);

  // Server-validated meeple placements (for fallback)
  const validMeeplePlacements = useMemo(() => {
    if (phase !== 'place_meeple' || !view.valid_actions) return [];
    return view.valid_actions.filter(
      (action: ValidAction) => isMeeplePlacementAction(action) || isSkipAction(action)
    );
  }, [phase, view.valid_actions]);

  // Deduplicated valid cells
  const validCells = useMemo(() => {
    const cellSet = new Map<string, { x: number; y: number }>();
    for (const action of validTilePlacements) {
      const key = `${action.x},${action.y}`;
      if (!cellSet.has(key)) cellSet.set(key, { x: action.x, y: action.y });
    }
    return Array.from(cellSet.values());
  }, [validTilePlacements]);

  // Valid rotations for selected cell
  const validRotationsForCell = useMemo(() => {
    if (!selectedCell) return [];
    return validTilePlacements
      .filter(a => a.x === selectedCell.x && a.y === selectedCell.y)
      .sort((a, b) => a.rotation - b.rotation);
  }, [validTilePlacements, selectedCell]);

  const currentPreview = validRotationsForCell[rotationIndex] || null;

  // Client-side meeple spots for confirmed placement
  const clientMeepleSpots: MeepleSpotInfo[] = useMemo(() => {
    if (uiPhase !== 'confirming_meeple' || !confirmedPlacement || !gameData.current_tile) return [];
    return getValidMeepleSpots(
      gameData.current_tile,
      confirmedPlacement.rotation,
      { x: confirmedPlacement.x, y: confirmedPlacement.y },
      gameData,
      view.viewer_id ?? '',
    );
  }, [uiPhase, confirmedPlacement, gameData, view.viewer_id]);

  // Reset on turn change
  useEffect(() => {
    setSelectedCell(null);
    setRotationIndex(0);
    setUiPhase('selecting_tile');
    setSelectedMeepleSpot(null);
    setBufferedMeeple(undefined);
    setConfirmedPlacement(null);
  }, [view.turn_number]);

  // Auto-send buffered meeple when server transitions to place_meeple
  useEffect(() => {
    if (phase !== 'place_meeple' || bufferedMeeple === undefined) return;

    if (bufferedMeeple === null) {
      onAction('place_meeple', { skip: true });
    } else {
      const spotStillValid = validMeeplePlacements.some(
        a => 'meeple_spot' in a && (a as { meeple_spot: string }).meeple_spot === bufferedMeeple
      );
      if (spotStillValid) {
        onAction('place_meeple', { meeple_spot: bufferedMeeple });
      } else {
        // Server rejected — fall back to showing meeple selection with server data
        setBufferedMeeple(undefined);
        setUiPhase('confirming_meeple');
        return;
      }
    }

    setBufferedMeeple(undefined);
    setSelectedCell(null);
    setRotationIndex(0);
    setUiPhase('selecting_tile');
    setSelectedMeepleSpot(null);
    setConfirmedPlacement(null);
  }, [phase, bufferedMeeple, validMeeplePlacements, onAction]);

  // Board click handler — only in selecting_tile phase
  const handleBoardClick = useCallback((x: number, y: number) => {
    if (uiPhase !== 'selecting_tile') return;

    const isValidCell = validCells.some(c => c.x === x && c.y === y);
    if (!isValidCell) {
      setSelectedCell(null);
      setRotationIndex(0);
      return;
    }

    if (selectedCell && selectedCell.x === x && selectedCell.y === y) {
      setRotationIndex((prev) => (prev + 1) % validRotationsForCell.length);
    } else {
      setSelectedCell({ x, y });
      setRotationIndex(0);
    }
  }, [uiPhase, validCells, selectedCell, validRotationsForCell.length]);

  // Confirm tile → transition to meeple phase
  const handleConfirmTile = useCallback(() => {
    if (!currentPreview) return;
    setConfirmedPlacement(currentPreview);
    setUiPhase('confirming_meeple');
    setSelectedMeepleSpot(null);
  }, [currentPreview]);

  // Meeple spot click — toggle selection
  const handleMeepleSpotClick = useCallback((spot: string) => {
    setSelectedMeepleSpot(prev => prev === spot ? null : spot);
  }, []);

  // Confirm meeple — buffer choice (or skip if none selected) and send tile placement
  const handleConfirmMeeple = useCallback(() => {
    if (!confirmedPlacement) return;

    // null selectedMeepleSpot means user confirmed without selecting a spot = skip meeple
    setBufferedMeeple(selectedMeepleSpot ?? null);
    setUiPhase('waiting');

    onAction('place_tile', {
      x: confirmedPlacement.x,
      y: confirmedPlacement.y,
      rotation: confirmedPlacement.rotation,
    });
  }, [confirmedPlacement, selectedMeepleSpot, onAction]);

  // Cancel meeple — go back to tile selection
  const handleCancelMeeple = useCallback(() => {
    setUiPhase('selecting_tile');
    setConfirmedPlacement(null);
    setSelectedMeepleSpot(null);
  }, []);

  // Fallback meeple handlers (server's place_meeple phase, no buffer)
  const handleFallbackMeeplePlaced = useCallback((spot: string) => {
    onAction('place_meeple', { meeple_spot: spot });
  }, [onAction]);

  const handleFallbackMeepleSkip = useCallback(() => {
    onAction('place_meeple', { skip: true });
  }, [onAction]);

  // Determine meeple spots to show
  const showMeeplePlacementMode = uiPhase === 'confirming_meeple' && isMyTurn;

  // Fallback: if server is at place_meeple and we have no buffer, use server spots
  const isFallbackMeepleMode = phase === 'place_meeple' && bufferedMeeple === undefined && uiPhase === 'confirming_meeple';

  const fallbackMeepleSpots: MeepleSpotInfo[] = useMemo(() => {
    if (!isFallbackMeepleMode) return [];
    // Convert server spots to MeepleSpotInfo using the placed tile info
    const lastPos = gameData.last_placed_position;
    if (!lastPos) return [];
    const [px, py] = lastPos.split(',').map(Number);
    const placedTile = gameData.board.tiles[lastPos];
    if (!placedTile) return [];
    return getValidMeepleSpots(
      placedTile.tile_type_id,
      placedTile.rotation,
      { x: px, y: py },
      gameData,
      view.viewer_id ?? '',
    );
  }, [isFallbackMeepleMode, gameData, view.viewer_id]);

  const activeMeepleSpots = isFallbackMeepleMode ? fallbackMeepleSpots : clientMeepleSpots;

  // Position for meeple overlay
  const meepleOverlayPosition = useMemo(() => {
    if (isFallbackMeepleMode && gameData.last_placed_position) {
      const [px, py] = gameData.last_placed_position.split(',').map(Number);
      return { x: px, y: py };
    }
    if (confirmedPlacement) return { x: confirmedPlacement.x, y: confirmedPlacement.y };
    return null;
  }, [isFallbackMeepleMode, gameData.last_placed_position, confirmedPlacement]);

  // Scores
  const scores = useMemo(() => {
    const scoreMap: Record<string, number> = {};
    view.players.forEach(player => {
      scoreMap[player.player_id] = gameData.scores?.[player.player_id] || 0;
    });
    return scoreMap;
  }, [view.players, gameData.scores]);

  const previewRotation = currentPreview?.rotation ?? 0;

  // Determine status text for TilePreview
  const getUiStatusPhase = (): string => {
    if (uiPhase === 'confirming_meeple') return 'confirming_meeple';
    if (uiPhase === 'waiting') return 'waiting';
    return phase;
  };

  return (
    <div className="flex h-full">
      {/* Board area */}
      <div className="flex-1 relative">
        <CarcassonneBoard
          gameData={gameData}
          players={view.players}
          validCells={validCells}
          selectedCell={selectedCell}
          currentPreview={uiPhase === 'selecting_tile' ? currentPreview : null}
          onCellClicked={handleBoardClick}
          isMyTurn={isMyTurn}
          phase={phase}
          showConfirmButton={uiPhase === 'selecting_tile' && selectedCell !== null && currentPreview !== null && isMyTurn}
          onConfirmTile={handleConfirmTile}
          meeplePlacementMode={showMeeplePlacementMode || isFallbackMeepleMode}
          meepleSpots={activeMeepleSpots}
          selectedMeepleSpot={selectedMeepleSpot}
          onMeepleSpotClick={isFallbackMeepleMode
            ? (spot) => { handleFallbackMeeplePlaced(spot); }
            : handleMeepleSpotClick}
          onConfirmMeeple={isFallbackMeepleMode
            ? () => { if (selectedMeepleSpot) handleFallbackMeeplePlaced(selectedMeepleSpot); else handleFallbackMeepleSkip(); }
            : handleConfirmMeeple}
          onSkipMeeple={isFallbackMeepleMode ? handleFallbackMeepleSkip : handleCancelMeeple}
          lastPlacedPosition={meepleOverlayPosition}
          playerMeepleImage={playerMeepleImage}
          playerSeatIndex={playerSeatIndex}
          confirmedTile={confirmedPlacement && gameData.current_tile ? {
            tileType: gameData.current_tile,
            x: confirmedPlacement.x,
            y: confirmedPlacement.y,
            rotation: confirmedPlacement.rotation,
          } : null}
        />
      </div>

      {/* Sidebar */}
      <div className="w-80 border-l bg-gray-50 p-4 flex flex-col gap-4 overflow-y-auto">
        <TilePreview
          currentTile={gameData.current_tile}
          selectedRotation={previewRotation}
          isMyTurn={isMyTurn}
          phase={getUiStatusPhase()}
          hasSelection={selectedCell !== null}
        />

        <MeepleSupply
          meepleSupply={gameData.meeple_supply || {}}
          players={view.players}
        />

        <ScoreBoard
          players={view.players}
          scores={scores}
          currentPlayerId={currentPlayerId ?? undefined}
          viewerId={view.viewer_id ?? undefined}
        />

        <div className="bg-white rounded-lg border shadow-sm px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-600">Tiles remaining:</span>
            <span className="text-lg font-bold">{gameData.tiles_remaining || 0}</span>
          </div>
        </div>

        <button
          className="bg-gray-200 hover:bg-gray-300 text-gray-700 text-xs px-3 py-2 rounded border"
          onClick={() => {
            const state = {
              board_tiles: gameData.board.tiles,
              features: gameData.features,
              tile_feature_map: gameData.tile_feature_map,
              current_tile: gameData.current_tile,
              meeple_supply: gameData.meeple_supply,
              scores: gameData.scores,
              phase,
              uiPhase,
              viewer_id: view.viewer_id,
              selected_cell: selectedCell,
              confirmed_placement: confirmedPlacement,
            };
            navigator.clipboard.writeText(JSON.stringify(state, null, 2));
          }}
        >
          Copy debug state
        </button>
      </div>
    </div>
  );
}
