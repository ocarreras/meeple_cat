'use client';

import { useState, useMemo } from 'react';
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
  const [selectedRotation, setSelectedRotation] = useState(0);

  // Extract game data
  const gameData = view.game_data as CarcassonneGameData;

  // Determine whose turn it is
  const currentAction = view.current_phase?.expected_actions?.[0];
  const currentPlayerId = currentAction?.player_id;

  // Filter valid actions by type — use view.valid_actions (top-level)
  const validTilePlacements = useMemo(() => {
    if (phase !== 'place_tile' || !view.valid_actions) {
      return [];
    }
    return view.valid_actions.filter(isTilePlacementAction) as TilePlacement[];
  }, [phase, view.valid_actions]);

  const validMeeplePlacements = useMemo(() => {
    if (phase !== 'place_meeple' || !view.valid_actions) {
      return [];
    }
    return view.valid_actions.filter(
      (action: ValidAction) => isMeeplePlacementAction(action) || isSkipAction(action)
    );
  }, [phase, view.valid_actions]);

  // Action handlers
  const handleTilePlaced = (x: number, y: number, rotation: number) => {
    onAction('place_tile', { x, y, rotation });
  };

  const handleMeeplePlaced = (spot: string) => {
    onAction('place_meeple', { meeple_spot: spot });
  };

  const handleMeepleSkip = () => {
    onAction('place_meeple', { skip: true });
  };

  // Prepare scores
  const scores = useMemo(() => {
    const scoreMap: Record<string, number> = {};
    view.players.forEach(player => {
      scoreMap[player.player_id] = gameData.scores?.[player.player_id] || 0;
    });
    return scoreMap;
  }, [view.players, gameData.scores]);

  return (
    <div className="flex h-full">
      {/* Board area */}
      <div className="flex-1 relative">
        <CarcassonneBoard
          gameData={gameData}
          players={view.players}
          validActions={validTilePlacements}
          onTilePlaced={handleTilePlaced}
          selectedRotation={selectedRotation}
          isMyTurn={isMyTurn}
          phase={phase}
        />
      </div>

      {/* Sidebar */}
      <div className="w-80 border-l bg-gray-50 p-4 flex flex-col gap-4 overflow-y-auto">
        {/* Tile Preview */}
        <TilePreview
          currentTile={gameData.current_tile}
          selectedRotation={selectedRotation}
          onRotationChange={setSelectedRotation}
          isMyTurn={isMyTurn}
          phase={phase}
        />

        {/* Meeple Placement (only during place_meeple phase) */}
        {phase === 'place_meeple' && (
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
