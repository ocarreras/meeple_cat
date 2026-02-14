'use client';

import { useState } from 'react';
import { getToken, createMatch } from '@/lib/api';

export default function Home() {
  const [player1Name, setPlayer1Name] = useState('Alice');
  const [player2Name, setPlayer2Name] = useState('Bob');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdGame, setCreatedGame] = useState<{
    matchId: string;
    token1: string;
    token2: string;
  } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setCreatedGame(null);

    try {
      // Get tokens for both players
      const { token: token1, user_id: user_id1 } = await getToken(player1Name);
      const { token: token2, user_id: user_id2 } = await getToken(player2Name);

      // Create match
      const { match_id } = await createMatch(token1, 'carcassonne', [player1Name, player2Name]);

      // Store both tokens in localStorage
      localStorage.setItem(
        'meeple_tokens',
        JSON.stringify({
          [user_id1]: token1,
          [user_id2]: token2,
        })
      );

      // Show links for both players
      setCreatedGame({
        matchId: match_id,
        token1,
        token2,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create game');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-green-50 to-blue-50 p-4">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-lg shadow-lg p-8">
          <h1 className="text-3xl font-bold text-center mb-8 text-gray-800">
            Meeple — Carcassonne
          </h1>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label
                htmlFor="player1"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                Player 1 Name
              </label>
              <input
                id="player1"
                type="text"
                value={player1Name}
                onChange={(e) => setPlayer1Name(e.target.value)}
                required
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition"
                placeholder="Enter player 1 name"
              />
            </div>

            <div>
              <label
                htmlFor="player2"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                Player 2 Name
              </label>
              <input
                id="player2"
                type="text"
                value={player2Name}
                onChange={(e) => setPlayer2Name(e.target.value)}
                required
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition"
                placeholder="Enter player 2 name"
              />
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-semibold py-3 px-4 rounded-lg transition duration-200 ease-in-out transform hover:scale-105 disabled:transform-none disabled:cursor-not-allowed"
            >
              {loading ? 'Creating Game...' : 'Start Game'}
            </button>
          </form>

          {createdGame && (
            <div className="mt-6 p-4 bg-green-50 border border-green-200 rounded-lg">
              <p className="text-sm font-medium text-green-800 mb-3">
                Game created! Open as:
              </p>
              <div className="space-y-2">
                <a
                  href={`/game/${createdGame.matchId}?token=${createdGame.token1}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block text-center bg-green-600 hover:bg-green-700 text-white py-2 px-4 rounded-lg text-sm transition"
                >
                  Player 1 ({player1Name})
                </a>
                <a
                  href={`/game/${createdGame.matchId}?token=${createdGame.token2}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block text-center bg-blue-600 hover:bg-blue-700 text-white py-2 px-4 rounded-lg text-sm transition"
                >
                  Player 2 ({player2Name})
                </a>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
