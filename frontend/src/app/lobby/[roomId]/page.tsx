'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';
import { useLobbyStore } from '@/stores/lobbyStore';
import {
  getRoom,
  joinRoom,
  leaveRoom,
  toggleReady,
  addBot,
  startRoom,
} from '@/lib/api';
import RoomDetail from '@/components/lobby/RoomDetail';
import type { Room } from '@/lib/types';

export default function RoomPage() {
  const params = useParams();
  const router = useRouter();
  const { t } = useTranslation();
  const roomId = params.roomId as string;

  const { user, token, initialized } = useAuthStore();
  const userId = user?.userId ?? null;

  const {
    loading,
    error,
    currentRoom,
    currentSeatIndex,
    setCurrentRoom,
    setLoading,
    setError,
  } = useLobbyStore();

  const [room, setRoom] = useState<Room | null>(null);

  // Redirect to login if not authenticated
  useEffect(() => {
    if (initialized && !user) {
      router.replace('/login');
    }
  }, [initialized, user, router]);

  // Fetch room data
  useEffect(() => {
    if (!user) return;

    const fetchRoom = async () => {
      try {
        const r = await getRoom(roomId);
        setRoom(r);

        // If we're in this room, sync current room state
        const mySeat = r.seats.find((s) => s.user_id === userId);
        if (mySeat) {
          setCurrentRoom(r, mySeat.seat_index);
        }

        // If game started, redirect
        if (r.status === 'in_game' && r.match_id) {
          const params = token ? `?token=${token}` : '';
          router.push(`/game/${r.match_id}${params}`);
        }
      } catch {
        setError(t('room.notFound'));
      }
    };

    fetchRoom();
    const interval = setInterval(fetchRoom, 2000);
    return () => clearInterval(interval);
  }, [user, token, roomId, userId, setCurrentRoom, setError, router]);

  const isInRoom = currentRoom?.room_id === roomId;

  const handleJoin = async () => {
    setLoading(true);
    setError(null);
    try {
      const { room: r, seat_index } = await joinRoom(roomId, token ?? undefined);
      setRoom(r);
      setCurrentRoom(r, seat_index);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('room.failedJoin'));
    } finally {
      setLoading(false);
    }
  };

  const handleLeave = async () => {
    setLoading(true);
    try {
      await leaveRoom(roomId, token ?? undefined);
      setCurrentRoom(null);
      router.push('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : t('room.failedLeave'));
    } finally {
      setLoading(false);
    }
  };

  const handleReady = async () => {
    try {
      const r = await toggleReady(roomId, token ?? undefined);
      setRoom(r);
      const mySeat = r.seats.find((s) => s.user_id === userId);
      setCurrentRoom(r, mySeat?.seat_index ?? currentSeatIndex);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('room.failedReady'));
    }
  };

  const handleAddBot = async () => {
    try {
      const r = await addBot(roomId, 'random', token ?? undefined);
      setRoom(r);
      setCurrentRoom(r, currentSeatIndex);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('room.failedBot'));
    }
  };

  const handleStart = async () => {
    setLoading(true);
    setError(null);
    try {
      const { match_id, tokens } = await startRoom(roomId, token ?? undefined);
      const gameToken = (userId && tokens[userId]) || token;
      const params = gameToken ? `?token=${gameToken}` : '';
      router.push(`/game/${match_id}${params}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('room.failedStart'));
      setLoading(false);
    }
  };

  // Show loading while initializing
  if (!initialized || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-green-50 to-blue-50">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-t-4 border-b-4 border-blue-600"></div>
      </div>
    );
  }

  // Loading room
  if (!room) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-green-50 to-blue-50">
        {error ? (
          <div className="bg-white rounded-lg shadow-lg p-8 max-w-md text-center">
            <p className="text-red-600 mb-4">{error}</p>
            <a
              href="/"
              className="text-blue-600 hover:text-blue-700 underline"
            >
              {t('room.backToLobby')}
            </a>
          </div>
        ) : (
          <div className="text-gray-500">{t('room.loadingRoom')}</div>
        )}
      </div>
    );
  }

  // Room view (inline, not modal)
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-green-50 to-blue-50 p-4">
      <div className="w-full max-w-lg">
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">
            {error}
          </div>
        )}
        <RoomDetail
          room={room}
          userId={userId}
          currentSeatIndex={isInRoom ? currentSeatIndex : null}
          isInRoom={isInRoom}
          loading={loading}
          onReady={handleReady}
          onLeave={handleLeave}
          onAddBot={handleAddBot}
          onRemoveBot={() => {}}
          onStart={handleStart}
          onJoin={handleJoin}
          onClose={() => router.push('/')}
        />
      </div>
    </div>
  );
}
