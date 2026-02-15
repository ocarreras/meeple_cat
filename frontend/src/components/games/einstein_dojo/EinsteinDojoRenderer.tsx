'use client';

import { useState, useMemo, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { PlayerView, EinsteinDojoGameData } from '@/lib/types';
import { useGameStore } from '@/stores/gameStore';
import { orientationInfo, orientationIndex, NUM_ORIENTATIONS, isValidPlacement } from '@/lib/einsteinPieces';
import EinsteinDojoBoard from './EinsteinDojoBoard';
import PieceTray from './PieceTray';
import ScoreBoard from '../../game/ScoreBoard';

const PLAYER_COLORS = ['#3b82f6', '#f97316'];

interface EinsteinDojoRendererProps {
  view: PlayerView;
  onAction: (actionType: string, payload: Record<string, unknown>) => void;
  isMyTurn: boolean;
  phase: string;
}

export default function EinsteinDojoRenderer({
  view,
  onAction,
  isMyTurn,
  phase,
}: EinsteinDojoRendererProps) {
  const { t } = useTranslation();
  const [currentOrientation, setCurrentOrientation] = useState(0);
  const [snapTarget, setSnapTarget] = useState<{ q: number; r: number } | null>(null);
  const [panelExpanded, setPanelExpanded] = useState(false);

  const gameData = view.game_data as EinsteinDojoGameData;
  const gameOver = useGameStore((state) => state.gameOver);
  const isGameOver = view.status === 'finished' || gameOver !== null;

  const currentPlayerId = view.current_phase?.expected_actions?.[0]?.player_id;
  const viewerPlayer = view.players.find(p => p.player_id === view.viewer_id);
  const playerSeatIndex = viewerPlayer?.seat_index ?? 0;
  const playerColor = PLAYER_COLORS[playerSeatIndex % PLAYER_COLORS.length];

  const myTilesRemaining = view.viewer_id
    ? gameData.tiles_remaining[view.viewer_id] ?? 0
    : 0;

  // Reset on turn change
  useEffect(() => {
    setSnapTarget(null);
    setPanelExpanded(false);
  }, [view.turn_number]);

  // Rotate: cycle through 6 rotations within current chirality
  const handleRotate = useCallback(() => {
    setCurrentOrientation(prev => {
      const { chirality, rotation } = orientationInfo(prev);
      const nextRotation = (rotation + 1) % 6;
      return orientationIndex(chirality, nextRotation);
    });
  }, []);

  // Flip: toggle chirality, keep rotation
  const handleFlip = useCallback(() => {
    setCurrentOrientation(prev => {
      const { chirality, rotation } = orientationInfo(prev);
      const nextChirality = chirality === 'A' ? 'B' : 'A';
      return orientationIndex(nextChirality, rotation);
    });
  }, []);

  // Board hex click: try to snap and place
  const handleHexClicked = useCallback((q: number, r: number) => {
    if (!isMyTurn || phase !== 'place_tile') return;

    // Check if this is a valid placement
    const valid = isValidPlacement(
      gameData.board.kite_owners,
      currentOrientation,
      q,
      r,
    );

    if (valid) {
      // If clicking on the current snap target, place the tile
      if (snapTarget && snapTarget.q === q && snapTarget.r === r) {
        onAction('place_tile', {
          anchor_q: q,
          anchor_r: r,
          orientation: currentOrientation,
        });
        setSnapTarget(null);
        return;
      }

      // Otherwise, set snap target
      setSnapTarget({ q, r });
    } else {
      // Try all orientations at this hex to see if any work
      let foundValid = false;
      for (let o = 0; o < NUM_ORIENTATIONS; o++) {
        if (isValidPlacement(gameData.board.kite_owners, o, q, r)) {
          setCurrentOrientation(o);
          setSnapTarget({ q, r });
          foundValid = true;
          break;
        }
      }
      if (!foundValid) {
        setSnapTarget(null);
      }
    }
  }, [isMyTurn, phase, gameData.board.kite_owners, currentOrientation, snapTarget, onAction]);

  // Ghost piece for board preview
  const ghostPiece = useMemo(() => {
    if (!snapTarget || !isMyTurn || phase !== 'place_tile') return null;

    const valid = isValidPlacement(
      gameData.board.kite_owners,
      currentOrientation,
      snapTarget.q,
      snapTarget.r,
    );

    return {
      orientation: currentOrientation,
      anchorQ: snapTarget.q,
      anchorR: snapTarget.r,
      valid,
    };
  }, [snapTarget, isMyTurn, phase, gameData.board.kite_owners, currentOrientation]);

  // Scores
  const scores = useMemo(() => {
    const scoreMap: Record<string, number> = {};
    view.players.forEach(player => {
      scoreMap[player.player_id] = gameData.scores?.[player.player_id] || 0;
    });
    return scoreMap;
  }, [view.players, gameData.scores]);

  // Mobile status text
  const getMobileStatus = (): string => {
    if (isGameOver) return t('game.status.gameOver');
    if (!isMyTurn) return t('game.status.opponentTurn');
    if (snapTarget) return t('game.status.tapToConfirm', 'Tap again to place');
    return t('game.status.tapToPlace');
  };

  return (
    <div className="flex flex-col md:flex-row h-full">
      {/* Board area */}
      <div className="flex-1 relative min-h-0">
        <EinsteinDojoBoard
          gameData={gameData}
          players={view.players}
          onHexClicked={handleHexClicked}
          isMyTurn={isMyTurn}
          phase={phase}
          ghostPiece={ghostPiece}
        />
        {isGameOver && gameOver && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/40">
            <div className="bg-white rounded-xl shadow-2xl p-6 max-w-sm mx-4 text-center">
              <h2 className="text-2xl font-bold mb-3">{t('game.status.gameOver')}</h2>
              <div className="space-y-2 mb-4">
                {view.players.map(p => {
                  const isWinner = gameOver.winners.includes(p.player_id);
                  const seatIdx = p.seat_index;
                  return (
                    <div
                      key={p.player_id}
                      className={`flex items-center justify-between px-3 py-2 rounded ${
                        isWinner ? 'bg-yellow-50 border border-yellow-300' : 'bg-gray-50'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <div
                          className="w-4 h-4 rounded-full"
                          style={{ backgroundColor: PLAYER_COLORS[seatIdx % PLAYER_COLORS.length] }}
                        />
                        <span className="font-medium">{p.display_name}</span>
                        {isWinner && <span className="text-yellow-600 text-sm font-bold">Winner!</span>}
                      </div>
                      <span className="text-lg font-bold">
                        {gameOver.final_scores[p.player_id] ?? 0}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Sidebar (desktop) / Bottom panel (mobile) */}
      <div className="border-t md:border-t-0 md:border-l md:w-80 bg-gray-50 flex flex-col md:overflow-y-auto">
        {/* Mobile compact header */}
        <button
          className="md:hidden flex items-center gap-2 px-3 py-2 w-full text-left"
          onClick={() => setPanelExpanded(prev => !prev)}
        >
          <span className="text-sm font-medium flex-1 truncate">
            {getMobileStatus()}
          </span>
          <div className="flex items-center gap-2 flex-shrink-0">
            {view.players.map(p => (
              <div key={p.player_id} className="flex items-center gap-1">
                <div
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: PLAYER_COLORS[p.seat_index % PLAYER_COLORS.length] }}
                />
                <span className="text-xs font-semibold tabular-nums">{scores[p.player_id] || 0}</span>
              </div>
            ))}
            <svg
              className={`w-4 h-4 text-gray-400 transition-transform ${panelExpanded ? 'rotate-180' : ''}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </button>

        {/* Full panel content */}
        <div className={`${panelExpanded ? 'flex' : 'hidden'} md:flex flex-col gap-4 p-4 overflow-y-auto`}>
          <PieceTray
            currentOrientation={currentOrientation}
            tilesRemaining={myTilesRemaining}
            onRotate={handleRotate}
            onFlip={handleFlip}
            isMyTurn={isMyTurn}
            playerColor={playerColor}
          />

          <ScoreBoard
            players={view.players}
            scores={scores}
            currentPlayerId={currentPlayerId ?? undefined}
            viewerId={view.viewer_id ?? undefined}
          />

          {/* Tiles remaining for both players */}
          <div className="bg-white rounded-lg border shadow-sm px-4 py-3">
            <div className="text-sm font-semibold mb-2">{t('game.tilesRemainingLabel', 'Tiles remaining')}</div>
            {view.players.map(p => (
              <div key={p.player_id} className="flex items-center justify-between py-1">
                <div className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: PLAYER_COLORS[p.seat_index % PLAYER_COLORS.length] }}
                  />
                  <span className="text-sm">{p.display_name}</span>
                </div>
                <span className="font-bold">{gameData.tiles_remaining[p.player_id] ?? 0}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
