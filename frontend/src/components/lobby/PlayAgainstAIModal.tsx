'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';
import { getGames, createMatch, type GameInfo } from '@/lib/api';

const CARCASSONNE_MAX_TILES = 71;

type Difficulty = 'mcts-easy' | 'mcts-medium' | 'mcts-hard';

const DIFFICULTIES: { id: Difficulty; labelKey: string; color: string; botName: string }[] = [
  { id: 'mcts-easy', labelKey: 'playAI.easy', color: 'bg-green-600 hover:bg-green-700', botName: 'Bot (Easy)' },
  { id: 'mcts-medium', labelKey: 'playAI.medium', color: 'bg-yellow-600 hover:bg-yellow-700', botName: 'Bot (Medium)' },
  { id: 'mcts-hard', labelKey: 'playAI.hard', color: 'bg-red-600 hover:bg-red-700', botName: 'Bot (Hard)' },
];

interface PlayAgainstAIModalProps {
  onClose: () => void;
}

export default function PlayAgainstAIModal({ onClose }: PlayAgainstAIModalProps) {
  const router = useRouter();
  const { t } = useTranslation();
  const { user, token: authToken } = useAuthStore();

  const [games, setGames] = useState<GameInfo[]>([]);
  const [selectedGameId, setSelectedGameId] = useState<string>('');
  const [difficulty, setDifficulty] = useState<Difficulty>('mcts-medium');
  const [tileCount, setTileCount] = useState(CARCASSONNE_MAX_TILES);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getGames().then((list) => {
      setGames(list);
      if (list.length > 0 && !selectedGameId) {
        setSelectedGameId(list[0].game_id);
      }
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedGame = games.find((g) => g.game_id === selectedGameId);
  const botInfo = DIFFICULTIES.find((d) => d.id === difficulty)!;

  const handleGameChange = (gameId: string) => {
    setSelectedGameId(gameId);
    setTileCount(CARCASSONNE_MAX_TILES);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const config: Record<string, unknown> = {};
      if (selectedGameId === 'carcassonne' && tileCount < CARCASSONNE_MAX_TILES) {
        config.tile_count = tileCount;
      }

      const { match_id } = await createMatch(
        authToken!,
        selectedGameId,
        [user!.displayName, botInfo.botName],
        { botSeats: [1], botId: difficulty, config },
      );

      router.push(`/game/${match_id}?token=${authToken}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('playAI.failed'));
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full">
        <div className="p-6">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-2xl font-bold text-gray-800">{t('playAI.title')}</h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 text-2xl leading-none p-1"
            >
              &times;
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Game selector */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('playAI.selectGame')}
              </label>
              {games.length <= 1 ? (
                <div className="px-4 py-2 bg-gray-100 border border-gray-300 rounded-lg text-gray-700">
                  {selectedGame?.display_name ?? '...'}
                </div>
              ) : (
                <div className="flex gap-2">
                  {games.map((game) => (
                    <button
                      key={game.game_id}
                      type="button"
                      onClick={() => handleGameChange(game.game_id)}
                      className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition ${
                        selectedGameId === game.game_id
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      {game.display_name}
                    </button>
                  ))}
                </div>
              )}
              {selectedGame?.description && (
                <p className="text-xs text-gray-500 mt-1">{selectedGame.description}</p>
              )}
            </div>

            {/* AI Difficulty */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('playAI.selectDifficulty')}
              </label>
              <div className="flex gap-2">
                {DIFFICULTIES.map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => setDifficulty(d.id)}
                    className={`flex-1 py-2.5 px-3 rounded-lg text-sm font-medium transition ${
                      difficulty === d.id
                        ? `${d.color} text-white`
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    {t(d.labelKey)}
                  </button>
                ))}
              </div>
            </div>

            {/* Game-specific options */}
            {selectedGameId === 'carcassonne' && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-sm font-medium text-gray-700">
                    {t('playAI.tiles')}
                  </label>
                  <span className="text-sm text-gray-500">
                    {tileCount} / {CARCASSONNE_MAX_TILES}
                  </span>
                </div>
                <input
                  type="range"
                  min={4}
                  max={CARCASSONNE_MAX_TILES}
                  value={tileCount}
                  onChange={(e) => setTileCount(Number(e.target.value))}
                  className="w-full accent-blue-600"
                />
                <div className="flex justify-between text-xs text-gray-400 mt-1">
                  <span>4</span>
                  <span>{t('playAI.fullGame', { count: CARCASSONNE_MAX_TILES })}</span>
                </div>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading || !selectedGameId}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-semibold py-3 px-4 rounded-lg transition"
            >
              {loading ? t('playAI.starting') : t('playAI.play')}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
