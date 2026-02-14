'use client';

import { create } from 'zustand';
import type { Room } from '@/lib/types';

export interface LobbyStore {
  // User state
  userId: string | null;
  displayName: string | null;
  token: string | null;

  // Lobby state
  rooms: Room[];
  loading: boolean;
  error: string | null;

  // Current room (when user is in one)
  currentRoom: Room | null;
  currentSeatIndex: number | null;

  // Actions
  setUser: (userId: string, displayName: string, token: string) => void;
  setRooms: (rooms: Room[]) => void;
  setCurrentRoom: (room: Room | null, seatIndex?: number | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

const initialState = {
  userId: null,
  displayName: null,
  token: null,
  rooms: [],
  loading: false,
  error: null,
  currentRoom: null,
  currentSeatIndex: null,
};

export const useLobbyStore = create<LobbyStore>((set) => ({
  ...initialState,

  setUser: (userId, displayName, token) =>
    set({ userId, displayName, token }),

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
