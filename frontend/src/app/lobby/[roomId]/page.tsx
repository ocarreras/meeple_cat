'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useLobbyStore } from '@/stores/lobbyStore';
import {
  getToken,
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
  const roomId = params.roomId as string;

  const {
    userId,
    token,
    loading,
    error,
    currentRoom,
    currentSeatIndex,
    setUser,
    setCurrentRoom,
    setLoading,
    setError,
  } = useLobbyStore();

  const [room, setRoom] = useState<Room | null>(null);
  const [loginName, setLoginName] = useState('');

  // Restore user from localStorage on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem('meeple_lobby_user');
      if (saved) {
        const { userId: id, displayName: name, token: t } = JSON.parse(saved);
        if (id && name && t) {
          setUser(id, name, t);
        }
      }
    } catch {
      // ignore
    }
  }, [setUser]);

  // Fetch room data
  useEffect(() => {
    if (!token) return;

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
          router.push(`/game/${r.match_id}?token=${token}`);
        }
      } catch {
        setError('Room not found');
      }
    };

    fetchRoom();
    const interval = setInterval(fetchRoom, 2000);
    return () => clearInterval(interval);
  }, [token, roomId, userId, setCurrentRoom, setError, router]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginName.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const { token: authToken, user_id } = await getToken(loginName.trim());
      setUser(user_id, loginName.trim(), authToken);
      localStorage.setItem(
        'meeple_lobby_user',
        JSON.stringify({
          userId: user_id,
          displayName: loginName.trim(),
          token: authToken,
        })
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const isInRoom = currentRoom?.room_id === roomId;

  const handleJoin = async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const { room: r, seat_index } = await joinRoom(token, roomId);
      setRoom(r);
      setCurrentRoom(r, seat_index);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to join');
    } finally {
      setLoading(false);
    }
  };

  const handleLeave = async () => {
    if (!token) return;
    setLoading(true);
    try {
      await leaveRoom(token, roomId);
      setCurrentRoom(null);
      router.push('/lobby');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to leave');
    } finally {
      setLoading(false);
    }
  };

  const handleReady = async () => {
    if (!token) return;
    try {
      const r = await toggleReady(token, roomId);
      setRoom(r);
      const mySeat = r.seats.find((s) => s.user_id === userId);
      setCurrentRoom(r, mySeat?.seat_index ?? currentSeatIndex);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle ready');
    }
  };

  const handleAddBot = async () => {
    if (!token) return;
    try {
      const r = await addBot(token, roomId);
      setRoom(r);
      setCurrentRoom(r, currentSeatIndex);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add bot');
    }
  };

  const handleStart = async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const { match_id, tokens } = await startRoom(token, roomId);
      const gameToken = (userId && tokens[userId]) || token;
      router.push(`/game/${match_id}?token=${gameToken}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start');
      setLoading(false);
    }
  };

  // Login screen
  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-green-50 to-blue-50 p-4">
        <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full">
          <h1 className="text-2xl font-bold text-center mb-2 text-gray-800">
            Join Room
          </h1>
          <p className="text-center text-gray-500 mb-6 text-sm">
            Enter your name to continue
          </p>

          <form onSubmit={handleLogin} className="space-y-4">
            <input
              type="text"
              value={loginName}
              onChange={(e) => setLoginName(e.target.value)}
              required
              autoFocus
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition text-gray-900 placeholder:text-gray-400"
              placeholder="Display name"
            />
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
              Continue
            </button>
          </form>
        </div>
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
              href="/lobby"
              className="text-blue-600 hover:text-blue-700 underline"
            >
              Back to lobby
            </a>
          </div>
        ) : (
          <div className="text-gray-500">Loading room...</div>
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
          onClose={() => router.push('/lobby')}
        />
      </div>
    </div>
  );
}
