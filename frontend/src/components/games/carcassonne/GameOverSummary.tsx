'use client';

import { Player, GameOverPayload, PlayerId } from '@/lib/types';

interface GameOverSummaryProps {
  players: Player[];
  finalScores: Record<PlayerId, number>;
  winners: PlayerId[];
  breakdown?: Record<PlayerId, Record<string, number>>;
}

const PLAYER_COLORS = ['#ef4444', '#3b82f6', '#22c55e', '#eab308', '#a855f7'];
const CATEGORIES = ['fields', 'cities', 'roads', 'monasteries'] as const;
const CATEGORY_LABELS: Record<string, string> = {
  fields: 'Fields',
  cities: 'Cities',
  roads: 'Roads',
  monasteries: 'Monasteries',
};

export default function GameOverSummary({
  players,
  finalScores,
  winners,
  breakdown,
}: GameOverSummaryProps) {
  const sortedPlayers = [...players].sort(
    (a, b) => (finalScores[b.player_id] || 0) - (finalScores[a.player_id] || 0)
  );

  const winnerNames = winners
    .map(id => players.find(p => p.player_id === id)?.display_name ?? id)
    .join(' & ');

  return (
    <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl p-4 md:p-6 max-w-lg w-full mx-4">
        <h2 className="text-2xl font-bold text-center mb-1">Game Over</h2>
        <p className="text-center text-lg mb-4">
          {winners.length === 1 ? (
            <><span className="font-semibold">{winnerNames}</span> wins!</>
          ) : (
            <>Tie: <span className="font-semibold">{winnerNames}</span></>
          )}
        </p>

        <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b-2">
              <th className="text-left py-2 pr-2">Player</th>
              {breakdown && CATEGORIES.map(cat => (
                <th key={cat} className="text-right py-2 px-1">{CATEGORY_LABELS[cat]}</th>
              ))}
              {breakdown && <th className="text-right py-2 px-1">End-Game</th>}
              <th className="text-right py-2 pl-2">Total</th>
            </tr>
          </thead>
          <tbody>
            {sortedPlayers.map((player) => {
              const isWinner = winners.includes(player.player_id);
              const playerBreakdown = breakdown?.[player.player_id];
              const endGameTotal = playerBreakdown
                ? CATEGORIES.reduce((sum, cat) => sum + (playerBreakdown[cat] || 0), 0)
                : null;

              return (
                <tr
                  key={player.player_id}
                  className={isWinner ? 'bg-yellow-50 font-semibold' : ''}
                >
                  <td className="py-2 pr-2">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: PLAYER_COLORS[player.seat_index % PLAYER_COLORS.length] }}
                      />
                      <span>{player.display_name}</span>
                      {isWinner && <span className="text-yellow-600 text-xs">&#9733;</span>}
                    </div>
                  </td>
                  {breakdown && CATEGORIES.map(cat => (
                    <td key={cat} className="text-right py-2 px-1 tabular-nums">
                      {playerBreakdown?.[cat] || 0}
                    </td>
                  ))}
                  {breakdown && (
                    <td className="text-right py-2 px-1 tabular-nums font-medium">
                      +{endGameTotal || 0}
                    </td>
                  )}
                  <td className="text-right py-2 pl-2 tabular-nums text-lg font-bold">
                    {finalScores[player.player_id] || 0}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      </div>
    </div>
  );
}
