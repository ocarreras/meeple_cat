'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';
import { getMe } from '@/lib/api';

export default function AuthCallbackPage() {
  const router = useRouter();
  const { t } = useTranslation();
  const { setUser, setToken } = useAuthStore();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function handleCallback() {
      try {
        // The backend set httpOnly cookies before redirecting here.
        // Fetch user info using those cookies.
        const userInfo = await getMe();
        setToken(null); // OIDC users don't need a Bearer token
        setUser({
          userId: userInfo.user_id,
          displayName: userInfo.display_name,
          avatarUrl: userInfo.avatar_url,
          isGuest: userInfo.is_guest,
          isAdmin: userInfo.is_admin,
        });
        router.replace('/');
      } catch (err) {
        console.error('Auth callback failed:', err);
        setError('Sign in failed. Please try again.');
      }
    }
    handleCallback();
  }, [setUser, setToken, router]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-green-50 to-blue-50 p-4">
        <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full text-center">
          <h2 className="text-xl font-bold text-red-600 mb-4">{t('auth.signInFailed')}</h2>
          <p className="text-gray-600 mb-6">{error}</p>
          <button
            onClick={() => router.push('/login')}
            className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-6 rounded-lg transition"
          >
            {t('auth.tryAgain')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-green-50 to-blue-50">
      <div className="text-center">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-t-4 border-b-4 border-blue-600"></div>
        <p className="mt-4 text-gray-600">{t('auth.signingIn')}</p>
      </div>
    </div>
  );
}
