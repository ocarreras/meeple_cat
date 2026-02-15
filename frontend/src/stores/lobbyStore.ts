'use client';

import { create } from 'zustand';
import type { Room } from '@/lib/types';

export interface LobbyStore {
  // Lobby state
  rooms: Room[];
  loading: boolean;
  error: string | null;

  // Current room (when user is in one)
  currentRoom: Room | null;
  currentSeatIndex: number | null;

  // Actions
  setRooms: (rooms: Room[]) => void;
  setCurrentRoom: (room: Room | null, seatIndex?: number | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

const initialState = {
  rooms: [],
  loading: false,
  error: null,
  currentRoom: null,
  currentSeatIndex: null,
};

export const useLobbyStore = create<LobbyStore>((set) => ({
  ...initialState,

  setRooms: (rooms) =>
    set({ rooms }),

  setCurrentRoom: (room, seatIndex = null) =>
    set({ currentRoom: room, currentSeatIndex: seatIndex }),

  setLoading: (loading) =>
    set({ loading }),

  setError: (error) =>
    set({ error }),

  reset: () => set(initialState),
}));
