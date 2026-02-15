'use client';

import type { Room, RoomSeat } from '@/lib/types';
import { useTranslation } from 'react-i18next';

interface RoomDetailProps {
  room: Room;
  userId: string | null;
  currentSeatIndex: number | null;
  isInRoom: boolean;
  loading: boolean;
  onReady: () => void;
  onLeave: () => void;
  onAddBot: () => void;
  onRemoveBot: (seatIndex: number) => void;
  onStart: () => void;
  onJoin: () => void;
  onClose: () => void;
}

const GAME_NAMES: Record<string, string> = {
  carcassonne: 'Carcassonne',
  einstein_dojo: 'Ein Stein Dojo',
};

function SeatRow({
  seat,
  isCurrentUser,
}: {
  seat: RoomSeat;
  isCurrentUser: boolean;
}) {
  const { t } = useTranslation();
  const isEmpty = !seat.user_id && !seat.is_bot;

  return (
    <div
      className={`flex items-center justify-between p-3 rounded-lg border-2 ${
        isCurrentUser
          ? 'border-blue-500 bg-blue-50'
          : isEmpty
            ? 'border-dashed border-gray-200 bg-gray-50'
            : 'border-gray-200 bg-white'
      }`}
    >
      <div className="flex items-center gap-3">
        <div
          className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
            isEmpty
              ? 'bg-gray-200 text-gray-400'
              : seat.is_bot
                ? 'bg-purple-100 text-purple-600'
                : 'bg-blue-100 text-blue-600'
          }`}
        >
          {seat.seat_index + 1}
        </div>
        <div>
          <div className="font-medium text-gray-800">
            {isEmpty
              ? t('room.emptySeat')
              : seat.is_bot
                ? `Bot (${seat.bot_id})`
                : seat.display_name}
          </div>
          {isCurrentUser && (
            <div className="text-xs text-blue-600">{t('common.you')}</div>
          )}
        </div>
      </div>
      {!isEmpty && (
        <div
          className={`px-3 py-1 rounded-full text-xs font-medium ${
            seat.is_ready
              ? 'bg-green-100 text-green-700'
              : 'bg-yellow-100 text-yellow-700'
          }`}
        >
          {seat.is_ready ? t('common.ready') : t('common.notReady')}
        </div>
      )}
    </div>
  );
}

export default function RoomDetail({
  room,
  userId,
  currentSeatIndex,
  isInRoom,
  loading,
  onReady,
  onLeave,
  onAddBot,
  onStart,
  onJoin,
  onClose,
}: RoomDetailProps) {
  const { t } = useTranslation();
  const isCreator = userId === room.created_by;
  const occupied = room.seats.filter((s) => s.user_id || s.is_bot);
  const allReady = occupied.every((s) => s.is_ready);
  const canStart = isCreator && allReady && occupied.length >= 2;
  const hasEmptySeat = room.seats.some((s) => !s.user_id && !s.is_bot);
  const isFull = !hasEmptySeat;
  const mySeat =
    currentSeatIndex !== null ? room.seats[currentSeatIndex] : null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          {/* Header */}
          <div className="flex justify-between items-start mb-6">
            <div>
              <h2 className="text-2xl font-bold text-gray-800">
                {GAME_NAMES[room.game_id] ?? room.game_id}
              </h2>
              <p className="text-sm text-gray-500">
                {t('room.hostedBy', { name: room.creator_name })}
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 text-2xl leading-none p-1"
            >
              &times;
            </button>
          </div>

          {/* Config info */}
          {room.config.tile_count != null && (
            <div className="text-sm text-gray-500 mb-4">
              {t('room.tiles', { count: Number(room.config.tile_count), max: 71 })}
            </div>
          )}

          {/* Seats */}
          <div className="space-y-2 mb-6">
            {room.seats.map((seat) => (
              <SeatRow
                key={seat.seat_index}
                seat={seat}
                isCurrentUser={seat.seat_index === currentSeatIndex}
              />
            ))}
          </div>

          {/* Actions */}
          <div className="space-y-2">
            {isInRoom ? (
              <>
                {/* Creator: add bot */}
                {isCreator && hasEmptySeat && (
                  <button
                    onClick={onAddBot}
                    disabled={loading}
                    className="w-full px-4 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-300 text-white rounded-lg font-medium transition text-sm"
                  >
                    {t('room.addBot')}
                  </button>
                )}

                {/* Non-creator: ready toggle */}
                {!isCreator && mySeat && (
                  <button
                    onClick={onReady}
                    disabled={loading}
                    className={`w-full px-4 py-2.5 rounded-lg font-medium transition text-sm ${
                      mySeat.is_ready
                        ? 'bg-yellow-500 hover:bg-yellow-600 text-white'
                        : 'bg-green-600 hover:bg-green-700 text-white'
                    }`}
                  >
                    {mySeat.is_ready ? t('room.unready') : t('common.ready')}
                  </button>
                )}

                {/* Creator: start */}
                {isCreator && (
                  <button
                    onClick={onStart}
                    disabled={!canStart || loading}
                    className="w-full px-4 py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white rounded-lg font-semibold transition"
                  >
                    {loading
                      ? t('room.starting')
                      : canStart
                        ? t('room.startGame')
                        : occupied.length < 2
                          ? t('room.needPlayers')
                          : t('room.waitingReady')}
                  </button>
                )}

                {/* Leave */}
                <button
                  onClick={onLeave}
                  disabled={loading}
                  className="w-full px-4 py-2.5 bg-red-100 hover:bg-red-200 text-red-700 rounded-lg font-medium transition text-sm"
                >
                  {isCreator ? t('room.closeRoom') : t('room.leaveRoom')}
                </button>
              </>
            ) : (
              /* Not in room: join */
              <button
                onClick={onJoin}
                disabled={isFull || loading}
                className="w-full px-4 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white rounded-lg font-semibold transition"
              >
                {isFull ? t('room.roomFull') : t('room.joinRoom')}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
