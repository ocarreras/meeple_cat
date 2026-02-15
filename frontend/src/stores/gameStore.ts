'use client';

import { create } from 'zustand';
import type { PlayerView, GameOverPayload } from '@/lib/types';

export interface DisconnectNotification {
  playerId: string;
  type: 'disconnected' | 'reconnected' | 'forfeited';
  gracePeriod?: number;
  timestamp: number;
}

export interface GameStore {
  // Connection state
  matchId: string | null;
  connected: boolean;
  playerId: string | null;

  // Game state (from server)
  view: PlayerView | null;
  gameOver: GameOverPayload | null;
  error: string | null;

  // UI state
  submitting: boolean;
  disconnectNotifications: DisconnectNotification[];

  // Actions
  setConnected: (connected: boolean, matchId?: string, playerId?: string) => void;
  setView: (view: PlayerView) => void;
  setGameOver: (payload: GameOverPayload) => void;
  setError: (error: string | null) => void;
  setSubmitting: (submitting: boolean) => void;
  addDisconnectNotification: (notification: DisconnectNotification) => void;
  removeDisconnectNotification: (playerId: string) => void;
  reset: () => void;
}

const initialState = {
  matchId: null,
  connected: false,
  playerId: null,
  view: null,
  gameOver: null,
  error: null,
  submitting: false,
  disconnectNotifications: [] as DisconnectNotification[],
};

export const useGameStore = create<GameStore>((set) => ({
  ...initialState,

  setConnected: (connected, matchId, playerId) =>
    set((state) => ({
      connected,
      matchId: matchId ?? state.matchId,
      playerId: playerId ?? state.playerId,
    })),

  setView: (view) =>
    set({
      view,
      error: null, // Clear error on successful state update
    }),

  setGameOver: (payload) =>
    set({
      gameOver: payload,
    }),

  setError: (error) =>
    set({
      error,
    }),

  setSubmitting: (submitting) =>
    set({
      submitting,
    }),

  addDisconnectNotification: (notification) =>
    set((state) => ({
      disconnectNotifications: [
        ...state.disconnectNotifications.filter(
          (n) => !(n.playerId === notification.playerId && n.type === 'disconnected')
        ),
        notification,
      ],
    })),

  removeDisconnectNotification: (playerId) =>
    set((state) => ({
      disconnectNotifications: state.disconnectNotifications.filter(
        (n) => n.playerId !== playerId
      ),
    })),

  reset: () => set(initialState),
}));
