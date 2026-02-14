'use client';

import { create } from 'zustand';
import type { PlayerView } from '@/lib/types';

export interface GameStore {
  // Connection state
  matchId: string | null;
  connected: boolean;
  playerId: string | null;

  // Game state (from server)
  view: PlayerView | null;
  error: string | null;

  // UI state
  submitting: boolean;

  // Actions
  setConnected: (connected: boolean, matchId?: string, playerId?: string) => void;
  setView: (view: PlayerView) => void;
  setError: (error: string | null) => void;
  setSubmitting: (submitting: boolean) => void;
  reset: () => void;
}

const initialState = {
  matchId: null,
  connected: false,
  playerId: null,
  view: null,
  error: null,
  submitting: false,
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

  setError: (error) =>
    set({
      error,
    }),

  setSubmitting: (submitting) =>
    set({
      submitting,
    }),

  reset: () => set(initialState),
}));
