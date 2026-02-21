'use client';

import { useTranslation } from 'react-i18next';

interface GameHeaderProps {
  phase: string;
  statusText?: string;
  currentPlayerName: string;
  isMyTurn: boolean;
  status: string;
}

export default function GameHeader({
  phase,
  statusText,
  currentPlayerName,
  isMyTurn,
  status
}: GameHeaderProps) {
  const { t } = useTranslation();

  const formatPhase = (phase: string): string => {
    const phaseMap: Record<string, string> = {
      'draw_tile': t('game.phase.drawTile'),
      'place_tile': t('game.phase.placeTile'),
      'place_meeple': t('game.phase.placeMeeple'),
      'score_check': t('game.phase.placeTile'),
      'game_over': t('game.phase.gameOver'),
      'player_turn': t('game.phase.playerTurn'),
      'choose_main_conflict': t('game.phase.chooseMainConflict'),
      'resolve_chain': t('game.phase.resolveChain'),
    };
    return phaseMap[phase] || phase.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  };

  return (
    <div className="bg-white border-b shadow-sm px-3 md:px-6 py-2 md:py-3 flex items-center justify-between">
      <div className="flex items-center gap-2 md:gap-6 flex-wrap min-w-0">
        <div className="hidden md:block">
          <span className="text-sm text-gray-500">{t('game.phase')}</span>
          <span className="ml-2 font-semibold">{formatPhase(phase)}</span>
        </div>
        {statusText && (
          <div className="hidden md:block">
            <span className="text-sm text-gray-500">{statusText}</span>
          </div>
        )}
        <div>
          <span className="hidden md:inline text-sm text-gray-500">{t('game.currentTurn')}</span>
          <span className="ml-0 md:ml-2 font-semibold text-sm md:text-base">
            {currentPlayerName}
            {isMyTurn && <span className="text-blue-600 ml-1">{t('common.you')}</span>}
          </span>
        </div>
      </div>
      <div className="flex-shrink-0 ml-2">
        <span className={`px-2 md:px-3 py-1 rounded-full text-xs md:text-sm font-medium ${
          status === 'active' ? 'bg-green-100 text-green-800'
          : status === 'abandoned' ? 'bg-yellow-100 text-yellow-800'
          : status === 'finished' ? 'bg-gray-100 text-gray-800'
          : 'bg-gray-100 text-gray-800'
        }`}>
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </span>
      </div>
    </div>
  );
}
