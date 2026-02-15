'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';
import { getMatchHistory } from '@/lib/api';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import type { MatchHistoryEntry } from '@/lib/types';

export default function ProfilePage() {
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const { user, initialized } = useAuthStore();
  const [matches, setMatches] = useState<MatchHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (initialized && !user) {
      router.replace('/login');
    }
  }, [initialized, user, router]);

  useEffect(() => {
    if (!user) return;

    async function fetchHistory() {
      try {
        const history = await getMatchHistory(user!.userId);
        setMatches(history);
      } catch {
        // Failed to load history
      } finally {
        setLoading(false);
      }
    }

    fetchHistory();
  }, [user]);

  if (!initialized || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-green-50 to-blue-50">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-t-4 border-b-4 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-green-50 to-blue-50">
      <div className="max-w-3xl mx-auto p-4 md:p-6">
        {/* Header */}
        <div className="flex items-center gap-4 mb-6">
          <button
            onClick={() => router.push('/')}
            className="text-gray-500 hover:text-gray-700 transition"
          >
            &larr; {t('common.back')}
          </button>
          <h1 className="text-2xl md:text-3xl font-bold text-gray-800">
            {t('profile.title')}
          </h1>
          <LanguageSwitcher />
        </div>

        {/* Profile card */}
        <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
          <div className="flex items-center gap-4">
            {user.avatarUrl ? (
              <img
                src={user.avatarUrl}
                alt={user.displayName}
                className="w-16 h-16 rounded-full"
              />
            ) : (
              <div className="w-16 h-16 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 text-2xl font-bold">
                {user.displayName.charAt(0).toUpperCase()}
              </div>
            )}
            <div>
              <h2 className="text-xl font-bold text-gray-800">
                {user.displayName}
              </h2>
              <p className="text-gray-500 text-sm">
                {user.isGuest ? t('profile.guestAccount') : t('profile.signedIn')}
              </p>
            </div>
          </div>
        </div>

        {/* Match history */}
        <div className="bg-white rounded-lg shadow-lg p-6">
          <h3 className="text-lg font-bold text-gray-800 mb-4">
            {t('profile.matchHistory')}
          </h3>

          {loading ? (
            <p className="text-gray-500 text-sm">{t('profile.loadingMatches')}</p>
          ) : matches.length === 0 ? (
            <p className="text-gray-500 text-sm">
              {t('profile.noMatches')}
            </p>
          ) : (
            <div className="space-y-3">
              {matches.map((match) => (
                <div
                  key={match.match_id}
                  className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition"
                >
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <span className="font-medium text-gray-800 capitalize">
                        {match.game_id}
                      </span>
                      <span
                        className={`ml-2 text-xs px-2 py-0.5 rounded-full ${
                          match.status === 'finished'
                            ? 'bg-gray-100 text-gray-600'
                            : match.status === 'active'
                              ? 'bg-green-100 text-green-700'
                              : 'bg-yellow-100 text-yellow-700'
                        }`}
                      >
                        {match.status}
                      </span>
                    </div>
                    {match.score !== null && (
                      <span className="text-sm font-medium text-gray-600">
                        {t('profile.score', { score: match.score })}
                      </span>
                    )}
                  </div>

                  <div className="text-sm text-gray-500">
                    <span>
                      {t('profile.playersLabel')}{' '}
                      {match.players
                        .map((p) => p.display_name)
                        .join(', ')}
                    </span>
                  </div>

                  {match.started_at && (
                    <div className="text-xs text-gray-400 mt-1">
                      {new Date(match.started_at).toLocaleDateString(i18n.language, {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
