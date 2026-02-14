'use client';

import { Player } from '@/lib/types';

interface MeepleSupplyProps {
  meepleSupply: Record<string, number>;
  players: Player[];
}

const PLAYER_COLORS = ['#ef4444', '#3b82f6', '#22c55e', '#eab308', '#a855f7'];

export default function MeepleSupply({ meepleSupply, players }: MeepleSupplyProps) {
  const sortedPlayers = [...players].sort((a, b) => a.seat_index - b.seat_index);

  return (
    <div className="bg-white rounded-lg border shadow-sm">
      <div className="px-4 py-2 border-b font-semibold">Meeples</div>
      <div className="p-3 space-y-2">
        {sortedPlayers.map((player) => {
          const playerColor = PLAYER_COLORS[player.seat_index % PLAYER_COLORS.length];
          const meepleCount = meepleSupply[player.player_id] || 0;

          return (
            <div key={player.player_id} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: playerColor }}
                />
                <span className="text-sm font-medium">{player.display_name}</span>
              </div>
              <span className="text-sm font-semibold">
                🧑 ×{meepleCount}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
