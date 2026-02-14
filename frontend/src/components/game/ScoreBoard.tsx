'use client';

import { Player } from '@/lib/types';

interface ScoreBoardProps {
  players: Player[];
  scores: Record<string, number>;
  currentPlayerId?: string;
  viewerId?: string;
}

const PLAYER_COLORS = ['#ef4444', '#3b82f6', '#22c55e', '#eab308', '#a855f7'];

export default function ScoreBoard({ players, scores, currentPlayerId, viewerId }: ScoreBoardProps) {
  const sortedPlayers = [...players].sort((a, b) => a.seat_index - b.seat_index);

  return (
    <div className="bg-white rounded-lg border shadow-sm">
      <div className="px-4 py-2 border-b font-semibold">Scores</div>
      <div className="divide-y">
        {sortedPlayers.map((player) => {
          const isCurrentPlayer = player.player_id === currentPlayerId;
          const isViewer = player.player_id === viewerId;
          const playerColor = PLAYER_COLORS[player.seat_index % PLAYER_COLORS.length];

          return (
            <div
              key={player.player_id}
              className={`px-4 py-2 flex items-center justify-between ${
                isCurrentPlayer ? 'bg-blue-50 border-l-4 border-blue-500' : ''
              }`}
            >
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded-full"
                  style={{ backgroundColor: playerColor }}
                />
                <span className="font-medium">
                  {player.display_name}
                  {isViewer && <span className="text-gray-500 text-sm ml-1">(You)</span>}
                </span>
              </div>
              <div className="font-semibold text-lg">
                {scores[player.player_id] || 0}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
