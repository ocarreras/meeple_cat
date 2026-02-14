'use client';

import type { Room } from '@/lib/types';

interface RoomCardProps {
  room: Room;
  onJoin: (roomId: string) => void;
  onView: (room: Room) => void;
  isCurrentUser: boolean;
}

const GAME_NAMES: Record<string, string> = {
  carcassonne: 'Carcassonne',
};

export default function RoomCard({ room, onJoin, onView, isCurrentUser }: RoomCardProps) {
  const occupiedSeats = room.seats.filter(
    (s) => s.user_id || s.is_bot
  ).length;
  const isFull = occupiedSeats >= room.max_players;

  return (
    <div
      className={`bg-white rounded-lg shadow-md p-4 hover:shadow-lg transition ${
        isCurrentUser ? 'ring-2 ring-blue-500' : ''
      }`}
    >
      <div className="flex justify-between items-start mb-3">
        <div>
          <h3 className="font-semibold text-lg text-gray-800">
            {GAME_NAMES[room.game_id] ?? room.game_id}
          </h3>
          <p className="text-sm text-gray-500">Host: {room.creator_name}</p>
        </div>
        <div className="text-right">
          <div className="text-sm font-medium text-gray-700">
            {occupiedSeats} / {room.max_players}
          </div>
          <div className="text-xs text-gray-500">players</div>
        </div>
      </div>

      {/* Seat fill bars */}
      <div className="flex gap-1.5 mb-4">
        {room.seats.map((seat) => (
          <div
            key={seat.seat_index}
            className={`flex-1 h-2 rounded-full ${
              seat.user_id || seat.is_bot
                ? seat.is_ready
                  ? 'bg-green-500'
                  : 'bg-yellow-400'
                : 'bg-gray-200'
            }`}
            title={
              seat.user_id
                ? `${seat.display_name}${seat.is_ready ? ' (ready)' : ''}`
                : seat.is_bot
                  ? `Bot (${seat.bot_id})`
                  : 'Empty'
            }
          />
        ))}
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => onView(room)}
          className="flex-1 px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm font-medium transition"
        >
          View
        </button>
        {!isCurrentUser && (
          <button
            onClick={() => onJoin(room.room_id)}
            disabled={isFull}
            className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition"
          >
            {isFull ? 'Full' : 'Join'}
          </button>
        )}
      </div>
    </div>
  );
}
