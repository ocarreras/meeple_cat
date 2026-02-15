'use client';

import { useEffect } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { getMe } from '@/lib/api';

export default function AuthInitializer({ children }: { children: React.ReactNode }) {
  const { setUser, setToken, setInitialized, initialized } = useAuthStore();

  useEffect(() => {
    if (initialized) return;

    async function init() {
      // 1. Try restoring from localStorage (guest users)
      try {
        const saved = localStorage.getItem('meeple_lobby_user');
        if (saved) {
          const { userId, displayName, token } = JSON.parse(saved);
          if (userId && displayName && token) {
            setToken(token);
            setUser({
              userId,
              displayName,
              avatarUrl: null,
              isGuest: true,
            });
            setInitialized(true);
            return;
          }
        }
      } catch {
        // ignore parse errors
      }

      // 2. Try cookie-based auth (OIDC users)
      try {
        const userInfo = await getMe();
        setToken(null);
        setUser({
          userId: userInfo.user_id,
          displayName: userInfo.display_name,
          avatarUrl: userInfo.avatar_url,
          isGuest: userInfo.is_guest,
        });
      } catch {
        // Not authenticated — that's fine
      }

      setInitialized(true);
    }

    init();
  }, [initialized, setUser, setToken, setInitialized]);

  return <>{children}</>;
}
