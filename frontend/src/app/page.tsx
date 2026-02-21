'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';
import { useLobbyStore } from '@/stores/lobbyStore';
import {
  listRooms,
  createRoom,
  joinRoom,
  leaveRoom,
  toggleReady,
  addBot,
  startRoom,
  getRoom,
} from '@/lib/api';
import RoomCard from '@/components/lobby/RoomCard';
import RoomDetail from '@/components/lobby/RoomDetail';
import CreateRoomModal from '@/components/lobby/CreateRoomModal';
import PlayAgainstAIModal from '@/components/lobby/PlayAgainstAIModal';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import type { Room } from '@/lib/types';

export default function LobbyPage() {
  const router = useRouter();
  const { t } = useTranslation();

  // Auth state from authStore
  const { user, token: authToken, initialized, logout: authLogout } = useAuthStore();

  // Lobby state
  const {
    rooms,
    currentRoom,
    currentSeatIndex,
    loading,
    error,
    setRooms,
    setCurrentRoom,
    setLoading,
    setError,
  } = useLobbyStore();

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [viewingRoom, setViewingRoom] = useState<Room | null>(null);
  const [showPlayAI, setShowPlayAI] = useState(false);

  // Derived values
  const userId = user?.userId ?? null;
  const displayName = user?.displayName ?? null;
  const token = authToken; // Bearer token for guest users

  // Redirect to login if not authenticated
  useEffect(() => {
    if (initialized && !user) {
      router.replace('/login');
    }
  }, [initialized, user, router]);

  // Poll rooms every 5 seconds
  useEffect(() => {
    if (!user) return;

    const fetchRooms = async () => {
      try {
        const roomList = await listRooms();
        setRooms(roomList);
      } catch {
        // silently ignore polling errors
      }
    };

    fetchRooms();
    const interval = setInterval(fetchRooms, 5000);
    return () => clearInterval(interval);
  }, [user, setRooms]);

  // Poll current room more frequently for real-time feel
  useEffect(() => {
    if (!user || !currentRoom) return;

    const fetchCurrentRoom = async () => {
      try {
        const room = await getRoom(currentRoom.room_id);
        setCurrentRoom(room, currentSeatIndex);

        // If game started, redirect
        if (room.status === 'in_game' && room.match_id) {
          const params = token ? `?token=${token}` : '';
          router.push(`/game/${room.match_id}${params}`);
        }
      } catch {
        // Room might have been deleted
        setCurrentRoom(null);
      }
    };

    const interval = setInterval(fetchCurrentRoom, 2000);
    return () => clearInterval(interval);
  }, [user, token, currentRoom, currentSeatIndex, setCurrentRoom, router]);

  const handleCreateRoom = useCallback(
    async (gameId: string, maxPlayers: number, config: Record<string, unknown>) => {
      setLoading(true);
      setError(null);

      try {
        const room = await createRoom(gameId, maxPlayers, config, token ?? undefined);
        setCurrentRoom(room, 0);
        setShowCreateModal(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : t('lobby.failedCreate'));
      } finally {
        setLoading(false);
      }
    },
    [token, setLoading, setError, setCurrentRoom]
  );

  const handleJoinRoom = useCallback(
    async (roomId: string) => {
      setLoading(true);
      setError(null);

      try {
        const { room, seat_index } = await joinRoom(roomId, token ?? undefined);
        setCurrentRoom(room, seat_index);
        setViewingRoom(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : t('lobby.failedJoin'));
      } finally {
        setLoading(false);
      }
    },
    [token, setLoading, setError, setCurrentRoom]
  );

  const handleLeaveRoom = useCallback(async () => {
    if (!currentRoom) return;
    setLoading(true);

    try {
      await leaveRoom(currentRoom.room_id, token ?? undefined);
      setCurrentRoom(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('lobby.failedLeave'));
    } finally {
      setLoading(false);
    }
  }, [token, currentRoom, setLoading, setError, setCurrentRoom]);

  const handleReady = useCallback(async () => {
    if (!currentRoom) return;

    try {
      const room = await toggleReady(currentRoom.room_id, token ?? undefined);
      const mySeat = room.seats.find((s) => s.user_id === userId);
      setCurrentRoom(room, mySeat?.seat_index ?? currentSeatIndex);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('lobby.failedReady'));
    }
  }, [token, currentRoom, userId, currentSeatIndex, setError, setCurrentRoom]);

  const handleAddBot = useCallback(async (botId: string) => {
    if (!currentRoom) return;

    try {
      const room = await addBot(currentRoom.room_id, botId, token ?? undefined);
      setCurrentRoom(room, currentSeatIndex);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('lobby.failedBot'));
    }
  }, [token, currentRoom, currentSeatIndex, setError, setCurrentRoom]);

  const handleStart = useCallback(async () => {
    if (!currentRoom) return;
    setLoading(true);
    setError(null);

    try {
      const { match_id, tokens } = await startRoom(currentRoom.room_id, token ?? undefined);
      const gameToken = (userId && tokens[userId]) || token;
      const params = gameToken ? `?token=${gameToken}` : '';
      router.push(`/game/${match_id}${params}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('lobby.failedStart'));
      setLoading(false);
    }
  }, [token, currentRoom, userId, setLoading, setError, router]);

  const handleLogout = useCallback(() => {
    authLogout();
    router.push('/login');
  }, [authLogout, router]);

  // Which room to show in the detail modal?
  const detailRoom = currentRoom || viewingRoom;
  const isInDetailRoom = !!currentRoom && detailRoom?.room_id === currentRoom.room_id;

  // Show nothing while initializing
  if (!initialized || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-green-50 to-blue-50">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-t-4 border-b-4 border-blue-600"></div>
      </div>
    );
  }

  // Lobby view
  return (
    <div className="min-h-screen bg-gradient-to-br from-green-50 to-blue-50">
      <div className="max-w-5xl mx-auto p-4 md:p-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-gray-800">
              {t('lobby.title')}
            </h1>
            <p className="text-gray-500 text-sm">
              {t('lobby.playingAs')}{' '}
              <span className="font-medium text-gray-700">
                {displayName}
              </span>
              {user.isGuest && (
                <span className="text-gray-400 ml-1">{t('common.guest')}</span>
              )}
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => router.push('/profile')}
              className="px-4 py-2.5 bg-white hover:bg-gray-50 text-gray-700 font-medium rounded-lg transition text-sm border border-gray-300"
            >
              {t('lobby.profile')}
            </button>
            {user.isAdmin && (
              <button
                onClick={() => router.push('/admin')}
                className="px-4 py-2.5 bg-red-50 hover:bg-red-100 text-red-700 font-medium rounded-lg transition text-sm border border-red-300"
              >
                {t('admin.title')}
              </button>
            )}
            <button
              onClick={() => setShowPlayAI(true)}
              className="px-4 py-2.5 bg-white hover:bg-gray-50 text-gray-700 font-medium rounded-lg transition text-sm border border-gray-300"
            >
              {t('lobby.playAgainstAI')}
            </button>
            <button
              onClick={() => setShowCreateModal(true)}
              disabled={!!currentRoom}
              className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition text-sm"
            >
              {t('lobby.createRoom')}
            </button>
            <button
              onClick={handleLogout}
              className="px-4 py-2.5 bg-white hover:bg-gray-50 text-gray-500 font-medium rounded-lg transition text-sm border border-gray-300"
            >
              {t('common.signOut')}
            </button>
            <LanguageSwitcher />
          </div>
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

        {/* "You are in a room" banner */}
        {currentRoom && (
          <div
            className="bg-blue-50 border border-blue-200 text-blue-700 px-4 py-3 rounded-lg mb-4 text-sm cursor-pointer hover:bg-blue-100 transition"
            onClick={() => setViewingRoom(null)}
          >
            {t('lobby.youAreInRoom', { creator: currentRoom.creator_name, game: currentRoom.game_id })}
          </div>
        )}

        {/* Room grid */}
        {rooms.length === 0 ? (
          <div className="text-center py-16 text-gray-500">
            <p className="text-lg mb-2">{t('lobby.noRooms')}</p>
            <p className="text-sm">{t('lobby.noRoomsHint')}</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {rooms.map((room) => (
              <RoomCard
                key={room.room_id}
                room={room}
                onJoin={handleJoinRoom}
                onView={(r) => {
                  if (currentRoom?.room_id === r.room_id) {
                    setViewingRoom(null);
                  } else {
                    setViewingRoom(r);
                  }
                }}
                isCurrentUser={currentRoom?.room_id === room.room_id}
              />
            ))}
          </div>
        )}
      </div>

      {/* Modals */}
      {showCreateModal && (
        <CreateRoomModal
          loading={loading}
          onClose={() => setShowCreateModal(false)}
          onCreate={handleCreateRoom}
        />
      )}

      {detailRoom && (
        <RoomDetail
          room={detailRoom}
          userId={userId}
          currentSeatIndex={isInDetailRoom ? currentSeatIndex : null}
          isInRoom={isInDetailRoom}
          loading={loading}
          onReady={handleReady}
          onLeave={handleLeaveRoom}
          onAddBot={handleAddBot}
          onRemoveBot={() => {}}
          onStart={handleStart}
          onJoin={() => handleJoinRoom(detailRoom.room_id)}
          onClose={() => setViewingRoom(null)}
        />
      )}

      {/* Play against AI modal */}
      {showPlayAI && (
        <PlayAgainstAIModal onClose={() => setShowPlayAI(false)} />
      )}
    </div>
  );
}
