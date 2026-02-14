'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useLobbyStore } from '@/stores/lobbyStore';
import {
  listRooms,
  getToken,
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
import type { Room } from '@/lib/types';

export default function LobbyPage() {
  const router = useRouter();
  const {
    userId,
    displayName,
    token,
    rooms,
    currentRoom,
    currentSeatIndex,
    loading,
    error,
    setUser,
    setRooms,
    setCurrentRoom,
    setLoading,
    setError,
  } = useLobbyStore();

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [viewingRoom, setViewingRoom] = useState<Room | null>(null);
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

  // Poll rooms every 5 seconds
  useEffect(() => {
    if (!token) return;

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
  }, [token, setRooms]);

  // Poll current room more frequently for real-time feel
  useEffect(() => {
    if (!token || !currentRoom) return;

    const fetchCurrentRoom = async () => {
      try {
        const room = await getRoom(currentRoom.room_id);
        setCurrentRoom(room, currentSeatIndex);

        // If game started, redirect
        if (room.status === 'in_game' && room.match_id) {
          // Find our token — we need to re-fetch it or use stored one
          router.push(`/game/${room.match_id}?token=${token}`);
        }
      } catch {
        // Room might have been deleted
        setCurrentRoom(null);
      }
    };

    const interval = setInterval(fetchCurrentRoom, 2000);
    return () => clearInterval(interval);
  }, [token, currentRoom, currentSeatIndex, setCurrentRoom, router]);

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

  const handleCreateRoom = useCallback(
    async (gameId: string, maxPlayers: number, config: Record<string, unknown>) => {
      if (!token) return;
      setLoading(true);
      setError(null);

      try {
        const room = await createRoom(token, gameId, maxPlayers, config);
        setCurrentRoom(room, 0);
        setShowCreateModal(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to create room');
      } finally {
        setLoading(false);
      }
    },
    [token, setLoading, setError, setCurrentRoom]
  );

  const handleJoinRoom = useCallback(
    async (roomId: string) => {
      if (!token) return;
      setLoading(true);
      setError(null);

      try {
        const { room, seat_index } = await joinRoom(token, roomId);
        setCurrentRoom(room, seat_index);
        setViewingRoom(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to join room');
      } finally {
        setLoading(false);
      }
    },
    [token, setLoading, setError, setCurrentRoom]
  );

  const handleLeaveRoom = useCallback(async () => {
    if (!token || !currentRoom) return;
    setLoading(true);

    try {
      await leaveRoom(token, currentRoom.room_id);
      setCurrentRoom(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to leave room');
    } finally {
      setLoading(false);
    }
  }, [token, currentRoom, setLoading, setError, setCurrentRoom]);

  const handleReady = useCallback(async () => {
    if (!token || !currentRoom) return;

    try {
      const room = await toggleReady(token, currentRoom.room_id);
      // Find our updated seat index
      const mySeat = room.seats.find((s) => s.user_id === userId);
      setCurrentRoom(room, mySeat?.seat_index ?? currentSeatIndex);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle ready');
    }
  }, [token, currentRoom, userId, currentSeatIndex, setError, setCurrentRoom]);

  const handleAddBot = useCallback(async () => {
    if (!token || !currentRoom) return;

    try {
      const room = await addBot(token, currentRoom.room_id);
      setCurrentRoom(room, currentSeatIndex);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add bot');
    }
  }, [token, currentRoom, currentSeatIndex, setError, setCurrentRoom]);

  const handleStart = useCallback(async () => {
    if (!token || !currentRoom) return;
    setLoading(true);
    setError(null);

    try {
      const { match_id, tokens } = await startRoom(token, currentRoom.room_id);
      // Use our user-specific token if available, otherwise current token
      const gameToken = (userId && tokens[userId]) || token;
      router.push(`/game/${match_id}?token=${gameToken}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start game');
      setLoading(false);
    }
  }, [token, currentRoom, userId, setLoading, setError, router]);

  // Which room to show in the detail modal?
  const detailRoom = currentRoom || viewingRoom;
  const isInDetailRoom = !!currentRoom && detailRoom?.room_id === currentRoom.room_id;

  // Login screen
  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-green-50 to-blue-50 p-4">
        <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full">
          <h1 className="text-3xl font-bold text-center mb-2 text-gray-800">
            Game Lobby
          </h1>
          <p className="text-center text-gray-500 mb-8">
            Enter your name to join
          </p>

          <form onSubmit={handleLogin} className="space-y-6">
            <div>
              <label
                htmlFor="displayName"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                Display Name
              </label>
              <input
                id="displayName"
                type="text"
                value={loginName}
                onChange={(e) => setLoginName(e.target.value)}
                required
                autoFocus
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
              {loading ? 'Entering...' : 'Enter Lobby'}
            </button>
          </form>
        </div>
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
              Game Lobby
            </h1>
            <p className="text-gray-500 text-sm">
              Playing as <span className="font-medium text-gray-700">{displayName}</span>
            </p>
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            disabled={!!currentRoom}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition text-sm"
          >
            Create Room
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

        {/* "You are in a room" banner */}
        {currentRoom && (
          <div
            className="bg-blue-50 border border-blue-200 text-blue-700 px-4 py-3 rounded-lg mb-4 text-sm cursor-pointer hover:bg-blue-100 transition"
            onClick={() => setViewingRoom(null)}
          >
            You are in a room ({currentRoom.creator_name}&apos;s{' '}
            {currentRoom.game_id}). Click here or the room below to manage it.
          </div>
        )}

        {/* Room grid */}
        {rooms.length === 0 ? (
          <div className="text-center py-16 text-gray-500">
            <p className="text-lg mb-2">No open rooms</p>
            <p className="text-sm">Create one to get started!</p>
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
                    // Clicking our own room opens detail
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
    </div>
  );
}
