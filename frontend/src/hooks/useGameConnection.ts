'use client';

import { useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useWebSocket } from './useWebSocket';
import { useGameStore } from '@/stores/gameStore';
import type { ServerMessage, ActionMessage, CommandWindowEntry } from '@/lib/types';
import {
  isStateUpdatePayload,
  isErrorPayload,
  isConnectedPayload,
  isGameOverPayload,
  isPlayerDisconnectedPayload,
  isGameEventsPayload,
} from '@/lib/types';
import { formatGameEvent } from '@/lib/eventFormatters';

interface GameConnectionReturn {
  sendAction: (action: ActionMessage) => void;
  connected: boolean;
  error: string | null;
}

export function useGameConnection(
  matchId: string,
  token?: string
): GameConnectionReturn {

  const router = useRouter();
  const setConnected = useGameStore((state) => state.setConnected);
  const setView = useGameStore((state) => state.setView);
  const setGameOver = useGameStore((state) => state.setGameOver);
  const setError = useGameStore((state) => state.setError);
  const addEvents = useGameStore((state) => state.addEvents);
  const addDisconnectNotification = useGameStore((state) => state.addDisconnectNotification);
  const removeDisconnectNotification = useGameStore((state) => state.removeDisconnectNotification);
  const connected = useGameStore((state) => state.connected);
  const error = useGameStore((state) => state.error);

  const handleMessage = useCallback(
    (message: ServerMessage) => {
      console.log('Received message:', message.type, message.payload);

      switch (message.type) {
        case 'connected': {
          if (isConnectedPayload(message.payload)) {
            setConnected(
              true,
              message.payload.match_id,
              message.payload.player_id
            );
          }
          break;
        }

        case 'state_update': {
          if (isStateUpdatePayload(message.payload)) {
            // Note: view is nested under payload.view
            setView(message.payload.view);
          }
          break;
        }

        case 'error': {
          if (isErrorPayload(message.payload)) {
            setError(message.payload.message);
          }
          break;
        }

        case 'game_events': {
          if (isGameEventsPayload(message.payload)) {
            const view = useGameStore.getState().view;
            const entries = message.payload.events
              .map((event) => formatGameEvent(event, view))
              .filter((e): e is CommandWindowEntry => e !== null);
            if (entries.length > 0) {
              addEvents(entries);
            }
          }
          break;
        }

        case 'game_over': {
          if (isGameOverPayload(message.payload)) {
            console.log('Game over:', message.payload);
            setGameOver(message.payload);
            setError(null);
            const view = useGameStore.getState().view;
            const winnerNames = message.payload.winners
              .map((id) => view?.players.find((p) => p.player_id === id)?.display_name ?? id)
              .join(' & ');
            addEvents([{
              id: `sys-gameover-${Date.now()}`,
              timestamp: Date.now(),
              type: 'system',
              text: `Game Over! Winner: ${winnerNames}`,
            }]);
          }
          break;
        }

        case 'pong': {
          // No-op, just for keepalive
          break;
        }

        case 'action_committed': {
          // Optional: handle action confirmation
          console.log('Action committed:', message.payload);
          break;
        }

        case 'player_disconnected': {
          if (isPlayerDisconnectedPayload(message.payload)) {
            addDisconnectNotification({
              playerId: message.payload.player_id,
              type: 'disconnected',
              gracePeriod: message.payload.grace_period_seconds,
              timestamp: Date.now(),
            });
          }
          break;
        }

        case 'player_reconnected': {
          const payload = message.payload as { player_id?: string };
          if (payload.player_id) {
            removeDisconnectNotification(payload.player_id);
            addDisconnectNotification({
              playerId: payload.player_id,
              type: 'reconnected',
              timestamp: Date.now(),
            });
            // Auto-clear reconnect notification after 3 seconds
            setTimeout(() => {
              removeDisconnectNotification(payload.player_id!);
            }, 3000);
          }
          break;
        }

        case 'player_forfeited': {
          const payload = message.payload as { player_id?: string };
          if (payload.player_id) {
            removeDisconnectNotification(payload.player_id);
            addDisconnectNotification({
              playerId: payload.player_id,
              type: 'forfeited',
              timestamp: Date.now(),
            });
          }
          break;
        }

        default: {
          console.warn('Unknown message type:', message.type);
        }
      }
    },
    [setConnected, setView, setGameOver, setError, addEvents, addDisconnectNotification, removeDisconnectNotification]
  );

  const handleConnect = useCallback(() => {
    console.log('WebSocket connected');
    // Don't set connected=true yet, wait for 'connected' message from server
  }, []);

  const handleDisconnect = useCallback((code?: number) => {
    console.log('WebSocket disconnected');
    setConnected(false);
    // Redirect to lobby on permanent failures (match gone, not authorized, etc.)
    if (code === 4004 || code === 4001 || code === 4003) {
      router.replace('/lobby');
    }
  }, [setConnected, router]);

  const { sendAction, sendPing, close } = useWebSocket({
    matchId,
    token,
    onMessage: handleMessage,
    onConnect: handleConnect,
    onDisconnect: handleDisconnect,
  });

  return {
    sendAction,
    connected,
    error,
  };
}
