'use client';

import { Suspense, useCallback } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import { useGameStore } from '@/stores/gameStore';
import { useGameConnection } from '@/hooks/useGameConnection';
import CarcassonneRenderer from '@/components/games/carcassonne/CarcassonneRenderer';
import GameHeader from '@/components/game/GameHeader';
import ConnectionStatus from '@/components/game/ConnectionStatus';
import type { ActionPayload } from '@/lib/types';

function LoadingSpinner() {
  return (
    <div className="h-screen flex items-center justify-center bg-gray-100">
      <div className="text-center">
        <div className="inline-block animate-spin rounded-full h-16 w-16 border-t-4 border-b-4 border-blue-600"></div>
        <p className="mt-4 text-gray-600 text-lg">Loading game...</p>
      </div>
    </div>
  );
}

function GamePageContent() {
  const params = useParams();
  const searchParams = useSearchParams();
  const matchId = params.matchId as string;
  const token = searchParams.get('token');

  const { sendAction } = useGameConnection(matchId, token!);
  const { view, connected, error } = useGameStore();

  const handleAction = useCallback((actionType: string, payload: Record<string, unknown>) => {
    sendAction({ action_type: actionType, payload: payload as unknown as ActionPayload });
  }, [sendAction]);

  if (!token) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-100">
        <div className="bg-white rounded-lg shadow-lg p-8 max-w-md">
          <h2 className="text-2xl font-bold text-red-600 mb-4">Missing Token</h2>
          <p className="text-gray-600">
            A valid authentication token is required to access this game.
          </p>
        </div>
      </div>
    );
  }

  if (!view) {
    return <LoadingSpinner />;
  }

  const currentPhase = view.current_phase;
  const isMyTurn = currentPhase.expected_actions?.[0]?.player_id === view.viewer_id;
  const currentPlayer = view.players.find(
    p => p.player_id === currentPhase.expected_actions?.[0]?.player_id
  );

  return (
    <div className="h-screen flex flex-col bg-gray-100">
      <GameHeader
        phase={currentPhase.name}
        tilesRemaining={view.game_data.tiles_remaining}
        currentPlayerName={currentPlayer?.display_name ?? ''}
        isMyTurn={isMyTurn}
        status={view.status}
      />
      <ConnectionStatus connected={connected} error={error} />
      <div className="flex-1 overflow-hidden">
        <CarcassonneRenderer
          view={view}
          onAction={handleAction}
          isMyTurn={isMyTurn}
          phase={currentPhase.name}
        />
      </div>
    </div>
  );
}

export default function GamePage() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <GamePageContent />
    </Suspense>
  );
}
