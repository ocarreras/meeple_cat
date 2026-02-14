'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { getToken, createMatch } from '@/lib/api';

const MAX_TILES = 71;

export default function Home() {
  const router = useRouter();
  const [showQuickPlay, setShowQuickPlay] = useState(false);
  const [playerName, setPlayerName] = useState('');
  const [tileCount, setTileCount] = useState(MAX_TILES);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleQuickPlay = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!playerName.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const { token, user_id } = await getToken(playerName.trim());
      const config: Record<string, unknown> = {};
      if (tileCount < MAX_TILES) {
        config.tile_count = tileCount;
      }

      const { match_id } = await createMatch(
        token,
        'carcassonne',
        [playerName.trim(), 'Bot (Random)'],
        { botSeats: [1], config }
      );

      localStorage.setItem(
        'meeple_tokens',
        JSON.stringify({ [user_id]: token })
      );

      router.push(`/game/${match_id}?token=${token}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start game');
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-green-50 to-blue-50 p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-10">
          <h1 className="text-5xl font-bold text-gray-800 mb-3">Meeple</h1>
          <p className="text-gray-500 text-lg">Board games, online</p>
        </div>

        {!showQuickPlay ? (
          <div className="space-y-3">
            <button
              onClick={() => router.push('/lobby')}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-4 px-6 rounded-lg transition text-lg"
            >
              Game Lobby
            </button>
            <button
              onClick={() => setShowQuickPlay(true)}
              className="w-full bg-white hover:bg-gray-50 text-gray-700 font-semibold py-4 px-6 rounded-lg transition text-lg border border-gray-300 shadow-sm"
            >
              Quick Play vs Bot
            </button>
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow-lg p-8">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-xl font-bold text-gray-800">
                Quick Play — Carcassonne
              </h2>
              <button
                onClick={() => setShowQuickPlay(false)}
                className="text-gray-400 hover:text-gray-600 text-xl leading-none"
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleQuickPlay} className="space-y-6">
              <div>
                <label
                  htmlFor="playerName"
                  className="block text-sm font-medium text-gray-700 mb-2"
                >
                  Your Name
                </label>
                <input
                  id="playerName"
                  type="text"
                  value={playerName}
                  onChange={(e) => setPlayerName(e.target.value)}
                  required
                  autoFocus
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition text-gray-900 placeholder:text-gray-400"
                  placeholder="Enter your name"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-sm font-medium text-gray-700">
                    Tiles
                  </label>
                  <span className="text-sm text-gray-500">
                    {tileCount} / {MAX_TILES}
                  </span>
                </div>
                <input
                  type="range"
                  min={4}
                  max={MAX_TILES}
                  value={tileCount}
                  onChange={(e) => setTileCount(Number(e.target.value))}
                  className="w-full accent-blue-600"
                />
                <div className="flex justify-between text-xs text-gray-400 mt-1">
                  <span>4</span>
                  <span>Full game ({MAX_TILES})</span>
                </div>
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
                {loading ? 'Starting...' : 'Play vs Bot'}
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
