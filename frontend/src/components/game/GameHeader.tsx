'use client';

interface GameHeaderProps {
  phase: string;
  tilesRemaining: number;
  currentPlayerName: string;
  isMyTurn: boolean;
  status: string;
}

function formatPhase(phase: string): string {
  const phaseMap: Record<string, string> = {
    'draw_tile': 'Drawing Tile',
    'place_tile': 'Place Tile',
    'place_meeple': 'Place Meeple',
    'game_over': 'Game Over',
  };
  return phaseMap[phase] || phase.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export default function GameHeader({
  phase,
  tilesRemaining,
  currentPlayerName,
  isMyTurn,
  status
}: GameHeaderProps) {
  return (
    <div className="bg-white border-b shadow-sm px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-6">
        <div>
          <span className="text-sm text-gray-500">Phase:</span>
          <span className="ml-2 font-semibold">{formatPhase(phase)}</span>
        </div>
        <div>
          <span className="text-sm text-gray-500">Tiles Remaining:</span>
          <span className="ml-2 font-semibold">{tilesRemaining}</span>
        </div>
        <div>
          <span className="text-sm text-gray-500">Current Turn:</span>
          <span className="ml-2 font-semibold">
            {currentPlayerName}
            {isMyTurn && <span className="text-blue-600 ml-1">(You)</span>}
          </span>
        </div>
      </div>
      <div>
        <span className={`px-3 py-1 rounded-full text-sm font-medium ${
          status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
        }`}>
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </span>
      </div>
    </div>
  );
}
