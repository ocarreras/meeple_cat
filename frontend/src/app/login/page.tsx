'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';
import { getToken, getProviders, getMe } from '@/lib/api';
import type { AuthProvider } from '@/lib/types';

export default function LoginPage() {
  const router = useRouter();
  const { user, setUser, setToken, initialized } = useAuthStore();
  const [guestName, setGuestName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [providers, setProviders] = useState<AuthProvider[]>([]);
  const [providersLoaded, setProvidersLoaded] = useState(false);

  // Load available providers
  useEffect(() => {
    getProviders()
      .then(setProviders)
      .catch(() => {})
      .finally(() => setProvidersLoaded(true));
  }, []);

  // Redirect if already logged in
  useEffect(() => {
    if (initialized && user) {
      router.replace('/lobby');
    }
  }, [initialized, user, router]);

  const handleGuestLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!guestName.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const { token, user_id } = await getToken(guestName.trim());
      setToken(token);
      setUser({
        userId: user_id,
        displayName: guestName.trim(),
        avatarUrl: null,
        isGuest: true,
      });
      localStorage.setItem(
        'meeple_lobby_user',
        JSON.stringify({
          userId: user_id,
          displayName: guestName.trim(),
          token,
        })
      );
      router.push('/lobby');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const handleProviderLogin = (providerId: string) => {
    // Full page redirect to OIDC flow
    window.location.href = `/api/v1/auth/${providerId}/login`;
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-green-50 to-blue-50 p-4">
      <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full">
        <h1 className="text-3xl font-bold text-center mb-2 text-gray-800">
          Sign In
        </h1>
        <p className="text-center text-gray-500 mb-8">
          Sign in to track your games and stats
        </p>

        {/* OIDC provider buttons */}
        {providers.length > 0 && (
          <div className="space-y-3 mb-6">
            {providers.map((provider) => (
              <button
                key={provider.provider_id}
                onClick={() => handleProviderLogin(provider.provider_id)}
                className="w-full bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 font-medium py-3 px-4 rounded-lg transition flex items-center justify-center gap-3"
              >
                {provider.provider_id === 'google' && (
                  <svg className="w-5 h-5" viewBox="0 0 24 24">
                    <path
                      fill="#4285F4"
                      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                    />
                    <path
                      fill="#34A853"
                      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                    />
                    <path
                      fill="#FBBC05"
                      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                    />
                    <path
                      fill="#EA4335"
                      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                    />
                  </svg>
                )}
                Sign in with {provider.display_name}
              </button>
            ))}
          </div>
        )}

        {/* Setup hint when no providers are configured */}
        {providersLoaded && providers.length === 0 && (
          <div className="bg-gray-50 border border-gray-200 text-gray-500 px-4 py-3 rounded-lg text-xs mb-6">
            Google Sign-In not configured. Set <code className="bg-gray-200 px-1 rounded">MEEPLE_GOOGLE_CLIENT_ID</code> and <code className="bg-gray-200 px-1 rounded">MEEPLE_GOOGLE_CLIENT_SECRET</code> in your backend <code className="bg-gray-200 px-1 rounded">.env</code> to enable it. See <code className="bg-gray-200 px-1 rounded">.env.example</code>.
          </div>
        )}

        {/* Divider */}
        {providers.length > 0 && (
          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-300" />
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-white text-gray-500">
                or continue as guest
              </span>
            </div>
          </div>
        )}

        {/* Guest login form */}
        <form onSubmit={handleGuestLogin} className="space-y-6">
          <div>
            <label
              htmlFor="guestName"
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              Display Name
            </label>
            <input
              id="guestName"
              type="text"
              value={guestName}
              onChange={(e) => setGuestName(e.target.value)}
              required
              autoFocus={providers.length === 0}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition text-gray-900 placeholder:text-gray-400"
              placeholder="Enter your name"
            />
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-semibold py-3 px-4 rounded-lg transition"
          >
            {loading ? 'Entering...' : 'Play as Guest'}
          </button>
        </form>
      </div>
    </div>
  );
}
