'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';
import {
  getAdminOverview,
  getAdminUsers,
  adminForceFinish,
  adminDeleteRoom,
  adminBanUser,
  adminUnbanUser,
} from '@/lib/api';
import type {
  AdminOverview,
  AdminUserInfo,
} from '@/lib/api';

type Tab = 'games' | 'users';

export default function AdminPage() {
  const router = useRouter();
  const { t } = useTranslation();
  const { user, initialized } = useAuthStore();

  const [tab, setTab] = useState<Tab>('games');
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [users, setUsers] = useState<AdminUserInfo[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Redirect non-admin users
  useEffect(() => {
    if (initialized && (!user || !user.isAdmin)) {
      router.replace('/');
    }
  }, [initialized, user, router]);

  // Fetch overview data
  const fetchOverview = useCallback(async () => {
    try {
      const data = await getAdminOverview();
      setOverview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load overview');
    }
  }, []);

  // Fetch users
  const fetchUsers = useCallback(async (query?: string) => {
    try {
      const data = await getAdminUsers(query);
      setUsers(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load users');
    }
  }, []);

  // Load data on tab change
  useEffect(() => {
    if (!user?.isAdmin) return;
    if (tab === 'games') {
      fetchOverview();
    } else {
      fetchUsers(search || undefined);
    }
  }, [tab, user, fetchOverview, fetchUsers, search]);

  // Debounced search
  useEffect(() => {
    if (tab !== 'users') return;
    const timer = setTimeout(() => {
      fetchUsers(search || undefined);
    }, 300);
    return () => clearTimeout(timer);
  }, [search, tab, fetchUsers]);

  const handleForceFinish = async (matchId: string) => {
    if (!window.confirm(t('admin.confirmForceFinish'))) return;
    setLoading(true);
    setError(null);
    try {
      await adminForceFinish(matchId);
      await fetchOverview();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to force finish');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteRoom = async (roomId: string) => {
    if (!window.confirm(t('admin.confirmDeleteRoom'))) return;
    setLoading(true);
    setError(null);
    try {
      await adminDeleteRoom(roomId);
      await fetchOverview();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete room');
    } finally {
      setLoading(false);
    }
  };

  const handleBan = async (userId: string) => {
    if (!window.confirm(t('admin.confirmBan'))) return;
    setLoading(true);
    setError(null);
    try {
      await adminBanUser(userId);
      await fetchUsers(search || undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to ban user');
    } finally {
      setLoading(false);
    }
  };

  const handleUnban = async (userId: string) => {
    if (!window.confirm(t('admin.confirmUnban'))) return;
    setLoading(true);
    setError(null);
    try {
      await adminUnbanUser(userId);
      await fetchUsers(search || undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to unban user');
    } finally {
      setLoading(false);
    }
  };

  if (!initialized || !user?.isAdmin) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-green-50 to-blue-50">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-t-4 border-b-4 border-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-green-50 to-blue-50">
      <div className="max-w-6xl mx-auto p-4 md:p-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-gray-800">
              {t('admin.title')}
            </h1>
          </div>
          <button
            onClick={() => router.push('/')}
            className="px-4 py-2.5 bg-white hover:bg-gray-50 text-gray-700 font-medium rounded-lg transition text-sm border border-gray-300"
          >
            {t('admin.backToLobby')}
          </button>
        </div>

        {/* Error banner */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm flex justify-between items-center">
            <span>{error}</span>
            <button
              onClick={() => setError(null)}
              className="text-red-400 hover:text-red-600 ml-2"
            >
              &times;
            </button>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-2 mb-6">
          <button
            onClick={() => setTab('games')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
              tab === 'games'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
            }`}
          >
            {t('admin.activeGames')}
          </button>
          <button
            onClick={() => setTab('users')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
              tab === 'users'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
            }`}
          >
            {t('admin.users')}
          </button>
        </div>

        {/* Active Games Tab */}
        {tab === 'games' && overview && (
          <div className="space-y-6">
            {/* Matches */}
            <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
              <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
                <h2 className="font-semibold text-gray-700">{t('admin.matches')}</h2>
              </div>
              {overview.active_matches.length === 0 ? (
                <div className="px-4 py-8 text-center text-gray-500 text-sm">
                  {t('admin.noMatches')}
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-100">
                        <th className="text-left px-4 py-2 text-gray-500 font-medium">{t('admin.game')}</th>
                        <th className="text-left px-4 py-2 text-gray-500 font-medium">{t('admin.players')}</th>
                        <th className="text-left px-4 py-2 text-gray-500 font-medium">{t('admin.status')}</th>
                        <th className="text-left px-4 py-2 text-gray-500 font-medium">{t('admin.activeSession')}</th>
                        <th className="text-left px-4 py-2 text-gray-500 font-medium">{t('admin.startedAt')}</th>
                        <th className="text-right px-4 py-2 text-gray-500 font-medium">{t('admin.actions')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overview.active_matches.map((match) => (
                        <tr key={match.match_id} className="border-b border-gray-50 hover:bg-gray-50">
                          <td className="px-4 py-2 font-medium">{match.game_id}</td>
                          <td className="px-4 py-2">
                            {match.players.map((p) => p.display_name).join(', ')}
                          </td>
                          <td className="px-4 py-2">
                            <span className="px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700">
                              {match.status}
                            </span>
                          </td>
                          <td className="px-4 py-2">
                            {match.has_active_session ? (
                              <span className="px-2 py-0.5 rounded-full text-xs bg-blue-100 text-blue-700">{t('admin.yes')}</span>
                            ) : (
                              <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-500">{t('admin.no')}</span>
                            )}
                          </td>
                          <td className="px-4 py-2 text-gray-500">
                            {match.started_at
                              ? new Date(match.started_at).toLocaleString()
                              : '-'}
                          </td>
                          <td className="px-4 py-2 text-right">
                            <button
                              onClick={() => handleForceFinish(match.match_id)}
                              disabled={loading}
                              className="px-3 py-1 text-xs bg-red-50 hover:bg-red-100 text-red-700 rounded border border-red-200 disabled:opacity-50"
                            >
                              {t('admin.forceFinish')}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Rooms */}
            <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
              <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
                <h2 className="font-semibold text-gray-700">{t('admin.rooms')}</h2>
              </div>
              {overview.active_rooms.length === 0 ? (
                <div className="px-4 py-8 text-center text-gray-500 text-sm">
                  {t('admin.noRooms')}
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-100">
                        <th className="text-left px-4 py-2 text-gray-500 font-medium">{t('admin.game')}</th>
                        <th className="text-left px-4 py-2 text-gray-500 font-medium">{t('admin.creator')}</th>
                        <th className="text-left px-4 py-2 text-gray-500 font-medium">{t('admin.status')}</th>
                        <th className="text-left px-4 py-2 text-gray-500 font-medium">{t('admin.players')}</th>
                        <th className="text-left px-4 py-2 text-gray-500 font-medium">{t('admin.createdAt')}</th>
                        <th className="text-right px-4 py-2 text-gray-500 font-medium">{t('admin.actions')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overview.active_rooms.map((room) => (
                        <tr key={room.room_id} className="border-b border-gray-50 hover:bg-gray-50">
                          <td className="px-4 py-2 font-medium">{room.game_id}</td>
                          <td className="px-4 py-2">{room.creator_name}</td>
                          <td className="px-4 py-2">
                            <span className={`px-2 py-0.5 rounded-full text-xs ${
                              room.status === 'in_game'
                                ? 'bg-green-100 text-green-700'
                                : 'bg-yellow-100 text-yellow-700'
                            }`}>
                              {room.status}
                            </span>
                          </td>
                          <td className="px-4 py-2">{room.player_count}/{room.max_players}</td>
                          <td className="px-4 py-2 text-gray-500">
                            {new Date(room.created_at).toLocaleString()}
                          </td>
                          <td className="px-4 py-2 text-right">
                            <button
                              onClick={() => handleDeleteRoom(room.room_id)}
                              disabled={loading}
                              className="px-3 py-1 text-xs bg-red-50 hover:bg-red-100 text-red-700 rounded border border-red-200 disabled:opacity-50"
                            >
                              {t('admin.deleteRoom')}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Users Tab */}
        {tab === 'users' && (
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center gap-3">
              <h2 className="font-semibold text-gray-700">{t('admin.users')}</h2>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t('admin.searchUsers')}
                className="flex-1 max-w-xs px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            {users.length === 0 ? (
              <div className="px-4 py-8 text-center text-gray-500 text-sm">
                {t('admin.noUsers')}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100">
                      <th className="text-left px-4 py-2 text-gray-500 font-medium">{t('admin.displayName')}</th>
                      <th className="text-left px-4 py-2 text-gray-500 font-medium">{t('admin.email')}</th>
                      <th className="text-left px-4 py-2 text-gray-500 font-medium">{t('admin.guestLabel')}</th>
                      <th className="text-left px-4 py-2 text-gray-500 font-medium">{t('admin.bannedLabel')}</th>
                      <th className="text-left px-4 py-2 text-gray-500 font-medium">{t('admin.gamesPlayed')}</th>
                      <th className="text-left px-4 py-2 text-gray-500 font-medium">{t('admin.createdAt')}</th>
                      <th className="text-right px-4 py-2 text-gray-500 font-medium">{t('admin.actions')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.user_id} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="px-4 py-2 font-medium">{u.display_name}</td>
                        <td className="px-4 py-2 text-gray-500">{u.email || '-'}</td>
                        <td className="px-4 py-2">
                          {u.is_guest ? (
                            <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-500">{t('admin.yes')}</span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full text-xs bg-blue-100 text-blue-700">{t('admin.no')}</span>
                          )}
                        </td>
                        <td className="px-4 py-2">
                          {u.is_banned ? (
                            <span className="px-2 py-0.5 rounded-full text-xs bg-red-100 text-red-700">{t('admin.yes')}</span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700">{t('admin.no')}</span>
                          )}
                        </td>
                        <td className="px-4 py-2">{u.games_played}</td>
                        <td className="px-4 py-2 text-gray-500">
                          {new Date(u.created_at).toLocaleDateString()}
                        </td>
                        <td className="px-4 py-2 text-right">
                          {u.user_id !== user.userId && (
                            u.is_banned ? (
                              <button
                                onClick={() => handleUnban(u.user_id)}
                                disabled={loading}
                                className="px-3 py-1 text-xs bg-green-50 hover:bg-green-100 text-green-700 rounded border border-green-200 disabled:opacity-50"
                              >
                                {t('admin.unban')}
                              </button>
                            ) : (
                              <button
                                onClick={() => handleBan(u.user_id)}
                                disabled={loading}
                                className="px-3 py-1 text-xs bg-red-50 hover:bg-red-100 text-red-700 rounded border border-red-200 disabled:opacity-50"
                              >
                                {t('admin.ban')}
                              </button>
                            )
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
