'use client';

import { Suspense, useCallback } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';
import { useGameStore } from '@/stores/gameStore';
import { useGameConnection } from '@/hooks/useGameConnection';
import CarcassonneRenderer from '@/components/games/carcassonne/CarcassonneRenderer';
import GameHeader from '@/components/game/GameHeader';
import ConnectionStatus from '@/components/game/ConnectionStatus';
import type { ActionPayload } from '@/lib/types';

function LoadingSpinner() {
  return (
    <div className="h-dvh flex items-center justify-center bg-gray-100">
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
  const urlToken = searchParams.get('token');
  const { token: authToken } = useAuthStore();

  // Use URL token if available (legacy guest flow), otherwise auth store token
  const token = urlToken || authToken || undefined;

  const { sendAction } = useGameConnection(matchId, token);
  const { view, connected, error } = useGameStore();

  const handleAction = useCallback((actionType: string, payload: Record<string, unknown>) => {
    sendAction({ action_type: actionType, payload: payload as unknown as ActionPayload });
  }, [sendAction]);

  if (!view) {
    return <LoadingSpinner />;
  }

  const currentPhase = view.current_phase;
  const isMyTurn = currentPhase.expected_actions?.[0]?.player_id === view.viewer_id;
  const currentPlayer = view.players.find(
    p => p.player_id === currentPhase.expected_actions?.[0]?.player_id
  );

  return (
    <div className="h-dvh flex flex-col bg-gray-100">
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
