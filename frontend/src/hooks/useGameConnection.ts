'use client';

import { useCallback } from 'react';
import { useWebSocket } from './useWebSocket';
import { useGameStore } from '@/stores/gameStore';
import type { ServerMessage, ActionMessage } from '@/lib/types';
import {
  isStateUpdatePayload,
  isErrorPayload,
  isConnectedPayload,
  isGameOverPayload,
} from '@/lib/types';

interface GameConnectionReturn {
  sendAction: (action: ActionMessage) => void;
  connected: boolean;
  error: string | null;
}

export function useGameConnection(
  matchId: string,
  token: string
): GameConnectionReturn {

  const setConnected = useGameStore((state) => state.setConnected);
  const setView = useGameStore((state) => state.setView);
  const setGameOver = useGameStore((state) => state.setGameOver);
  const setError = useGameStore((state) => state.setError);
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

        case 'game_over': {
          if (isGameOverPayload(message.payload)) {
            console.log('Game over:', message.payload);
            setGameOver(message.payload);
            setError(null);
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

        default: {
          console.warn('Unknown message type:', message.type);
        }
      }
    },
    [setConnected, setView, setGameOver, setError]
  );

  const handleConnect = useCallback(() => {
    console.log('WebSocket connected');
    // Don't set connected=true yet, wait for 'connected' message from server
  }, []);

  const handleDisconnect = useCallback(() => {
    console.log('WebSocket disconnected');
    setConnected(false);
  }, [setConnected]);

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
