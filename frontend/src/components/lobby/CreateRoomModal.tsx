'use client';

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { getGames, type GameInfo } from '@/lib/api';

interface CreateRoomModalProps {
  loading: boolean;
  onClose: () => void;
  onCreate: (gameId: string, maxPlayers: number, config: Record<string, unknown>) => void;
}

const CARCASSONNE_MAX_TILES = 71;

export default function CreateRoomModal({
  loading,
  onClose,
  onCreate,
}: CreateRoomModalProps) {
  const { t } = useTranslation();
  const [games, setGames] = useState<GameInfo[]>([]);
  const [selectedGameId, setSelectedGameId] = useState<string>('');
  const [maxPlayers, setMaxPlayers] = useState(2);
  const [tileCount, setTileCount] = useState(CARCASSONNE_MAX_TILES);

  useEffect(() => {
    getGames().then((list) => {
      setGames(list);
      if (list.length > 0 && !selectedGameId) {
        setSelectedGameId(list[0].game_id);
        setMaxPlayers(list[0].min_players);
      }
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedGame = games.find(g => g.game_id === selectedGameId);
  const minP = selectedGame?.min_players ?? 2;
  const maxP = selectedGame?.max_players ?? 2;

  const handleGameChange = (gameId: string) => {
    setSelectedGameId(gameId);
    const game = games.find(g => g.game_id === gameId);
    if (game) {
      setMaxPlayers(game.min_players);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const config: Record<string, unknown> = {};
    if (selectedGameId === 'carcassonne' && tileCount < CARCASSONNE_MAX_TILES) {
      config.tile_count = tileCount;
    }
    onCreate(selectedGameId, maxPlayers, config);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full">
        <div className="p-6">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-2xl font-bold text-gray-800">{t('createRoom.title')}</h2>
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
                {t('createRoom.game')}
              </label>
              {games.length <= 1 ? (
                <div className="px-4 py-2 bg-gray-100 border border-gray-300 rounded-lg text-gray-700">
                  {selectedGame?.display_name ?? '...'}
                </div>
              ) : (
                <div className="flex gap-2">
                  {games.map(game => (
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

            {/* Player count (only if range > 1) */}
            {maxP > minP && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  {t('createRoom.players')}
                </label>
                <div className="flex gap-2">
                  {Array.from(
                    { length: maxP - minP + 1 },
                    (_, i) => minP + i
                  ).map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setMaxPlayers(n)}
                      className={`flex-1 py-2 rounded-lg text-sm font-medium transition ${
                        maxPlayers === n
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Carcassonne-specific: tile count */}
            {selectedGameId === 'carcassonne' && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-sm font-medium text-gray-700">
                    {t('createRoom.tiles')}
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
                  <span>{t('createRoom.fullGame', { count: CARCASSONNE_MAX_TILES })}</span>
                </div>
              </div>
            )}

            <div className="flex gap-3">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 px-4 py-3 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg font-medium transition"
              >
                {t('common.cancel')}
              </button>
              <button
                type="submit"
                disabled={loading || !selectedGameId}
                className="flex-1 px-4 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-lg font-medium transition"
              >
                {loading ? t('createRoom.creating') : t('common.create')}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
