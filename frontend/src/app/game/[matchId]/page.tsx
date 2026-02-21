'use client';

import { Suspense, useCallback, useRef } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';
import { useGameStore } from '@/stores/gameStore';
import { useGameConnection } from '@/hooks/useGameConnection';
import CarcassonneRenderer from '@/components/games/carcassonne/CarcassonneRenderer';
import EinsteinDojoRenderer from '@/components/games/einstein_dojo/EinsteinDojoRenderer';
import GameHeader from '@/components/game/GameHeader';
import ConnectionStatus from '@/components/game/ConnectionStatus';
import DisconnectBanner from '@/components/game/DisconnectBanner';
import CommandWindow from '@/components/game/CommandWindow';
import type { ActionPayload, CarcassonneGameData, EinsteinDojoGameData } from '@/lib/types';

function LoadingSpinner() {
  const { t } = useTranslation();
  return (
    <div className="h-dvh flex items-center justify-center bg-gray-100">
      <div className="text-center">
        <div className="inline-block animate-spin rounded-full h-16 w-16 border-t-4 border-b-4 border-blue-600"></div>
        <p className="mt-4 text-gray-600 text-lg">{t('game.loadingGame')}</p>
      </div>
    </div>
  );
}

function GamePageContent() {
  const { t } = useTranslation();
  const params = useParams();
  const searchParams = useSearchParams();
  const matchId = params.matchId as string;
  const urlToken = searchParams.get('token');
  const { token: authToken } = useAuthStore();

  // Use URL token if available (legacy guest flow), otherwise auth store token
  const token = urlToken || authToken || undefined;

  const { sendAction } = useGameConnection(matchId, token);
  const { view, connected, error, gameOver } = useGameStore();

  const handleAction = useCallback((actionType: string, payload: Record<string, unknown>) => {
    sendAction({ action_type: actionType, payload: payload as unknown as ActionPayload });
  }, [sendAction]);

  const panHandlerRef = useRef<((tiles: string[]) => void) | null>(null);
  const handleRegisterPan = useCallback((handler: (tiles: string[]) => void) => {
    panHandlerRef.current = handler;
  }, []);
  const handlePanToTiles = useCallback((tiles: string[]) => {
    panHandlerRef.current?.(tiles);
  }, []);

  if (!view) {
    return <LoadingSpinner />;
  }

  const currentPhase = view.current_phase;
  const isMyTurn = currentPhase.expected_actions?.[0]?.player_id === view.viewer_id
    || (currentPhase.name === 'choose_main_conflict'
      && currentPhase.expected_actions?.some(a => a.player_id === view.viewer_id));
  const currentPlayer = view.players.find(
    p => p.player_id === currentPhase.expected_actions?.[0]?.player_id
  );

  // Build status text based on game type
  const getStatusText = (): string | undefined => {
    if (view.game_id === 'carcassonne') {
      const gameData = view.game_data as CarcassonneGameData;
      return `${t('game.tilesRemaining')}: ${gameData.tiles_remaining}`;
    }
    if (view.game_id === 'einstein_dojo') {
      const gameData = view.game_data as EinsteinDojoGameData;
      const viewerId = view.viewer_id;
      const myTiles = viewerId ? gameData.tiles_remaining[viewerId] ?? 0 : 0;
      return `${t('game.tilesRemaining')}: ${myTiles}`;
    }
    return undefined;
  };

  // Render the appropriate game component
  const renderGame = () => {
    if (view.game_id === 'einstein_dojo') {
      return (
        <EinsteinDojoRenderer
          view={view}
          onAction={handleAction}
          isMyTurn={isMyTurn}
          phase={currentPhase.name}
        />
      );
    }
    // Default: Carcassonne
    return (
      <CarcassonneRenderer
        view={view}
        onAction={handleAction}
        isMyTurn={isMyTurn}
        phase={currentPhase.name}
        onRegisterPanHandler={handleRegisterPan}
      />
    );
  };

  return (
    <div className="h-dvh flex flex-col bg-gray-100">
      <GameHeader
        phase={currentPhase.name}
        statusText={getStatusText()}
        currentPlayerName={currentPlayer?.display_name ?? ''}
        isMyTurn={isMyTurn}
        status={view.status}
      />
      <ConnectionStatus connected={connected} error={error} />
      <DisconnectBanner />
      <div className="flex-1 overflow-hidden">
        {renderGame()}
      </div>
      <CommandWindow onPanToTiles={handlePanToTiles} />
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
