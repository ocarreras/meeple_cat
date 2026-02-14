'use client';

import { useState } from 'react';

interface CreateRoomModalProps {
  loading: boolean;
  onClose: () => void;
  onCreate: (gameId: string, maxPlayers: number, config: Record<string, unknown>) => void;
}

const MAX_TILES = 71;
const MIN_PLAYERS = 2;
const MAX_PLAYERS = 5;

export default function CreateRoomModal({
  loading,
  onClose,
  onCreate,
}: CreateRoomModalProps) {
  const [maxPlayers, setMaxPlayers] = useState(2);
  const [tileCount, setTileCount] = useState(MAX_TILES);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const config: Record<string, unknown> = {};
    if (tileCount < MAX_TILES) {
      config.tile_count = tileCount;
    }
    onCreate('carcassonne', maxPlayers, config);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full">
        <div className="p-6">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-2xl font-bold text-gray-800">Create Room</h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 text-2xl leading-none p-1"
            >
              &times;
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Game
              </label>
              <div className="px-4 py-2 bg-gray-100 border border-gray-300 rounded-lg text-gray-700">
                Carcassonne
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Players
              </label>
              <div className="flex gap-2">
                {Array.from(
                  { length: MAX_PLAYERS - MIN_PLAYERS + 1 },
                  (_, i) => MIN_PLAYERS + i
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

            <div className="flex gap-3">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 px-4 py-3 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg font-medium transition"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="flex-1 px-4 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-lg font-medium transition"
              >
                {loading ? 'Creating...' : 'Create'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
