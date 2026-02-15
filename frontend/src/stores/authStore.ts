'use client';

import { create } from 'zustand';

export interface AuthUser {
  userId: string;
  displayName: string;
  avatarUrl: string | null;
  isGuest: boolean;
}

export interface AuthStore {
  user: AuthUser | null;
  token: string | null; // Only set for guest users (Bearer token)
  loading: boolean;
  initialized: boolean;

  setUser: (user: AuthUser | null) => void;
  setToken: (token: string | null) => void;
  setLoading: (loading: boolean) => void;
  setInitialized: (initialized: boolean) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  token: null,
  loading: false,
  initialized: false,

  setUser: (user) => set({ user }),
  setToken: (token) => set({ token }),
  setLoading: (loading) => set({ loading }),
  setInitialized: (initialized) => set({ initialized }),

  logout: () => {
    localStorage.removeItem('meeple_lobby_user');
    localStorage.removeItem('meeple_tokens');
    set({ user: null, token: null });
  },
}));
