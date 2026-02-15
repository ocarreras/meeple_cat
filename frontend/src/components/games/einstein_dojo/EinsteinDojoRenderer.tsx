'use client';

import { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { PlayerView, EinsteinDojoGameData } from '@/lib/types';
import { useGameStore } from '@/stores/gameStore';
import { orientationInfo, orientationIndex, NUM_ORIENTATIONS, isValidPlacement } from '@/lib/einsteinPieces';
import EinsteinDojoBoard, { type BoardHandle, type GhostPiece } from './EinsteinDojoBoard';
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
  const boardRef = useRef<BoardHandle>(null);

  const [currentOrientation, setCurrentOrientation] = useState(0);
  const [hoverHex, setHoverHex] = useState<{ q: number; r: number } | null>(null);
  const [isDraggingFromTray, setIsDraggingFromTray] = useState(false);
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

  // Refs for window event handlers (avoid stale closures)
  const currentOrientationRef = useRef(currentOrientation);
  currentOrientationRef.current = currentOrientation;
  const kiteOwnersRef = useRef(gameData.board.kite_owners);
  kiteOwnersRef.current = gameData.board.kite_owners;

  // Reset on turn change
  useEffect(() => {
    setHoverHex(null);
    setIsDraggingFromTray(false);
    setPanelExpanded(false);
  }, [view.turn_number]);

  // ── Rotate / Flip ──

  const handleRotate = useCallback(() => {
    setCurrentOrientation(prev => {
      const { chirality, rotation } = orientationInfo(prev);
      return orientationIndex(chirality, (rotation + 1) % 6);
    });
  }, []);

  const handleFlip = useCallback(() => {
    setCurrentOrientation(prev => {
      const { chirality, rotation } = orientationInfo(prev);
      return orientationIndex(chirality === 'A' ? 'B' : 'A', rotation);
    });
  }, []);

  // ── Board hover → live ghost ──

  const handleHoverHex = useCallback((q: number, r: number) => {
    setHoverHex(prev => {
      if (prev && prev.q === q && prev.r === r) return prev;
      return { q, r };
    });
  }, []);

  const handleHoverLeave = useCallback(() => {
    if (!isDraggingFromTray) setHoverHex(null);
  }, [isDraggingFromTray]);

  // ── Click to place ──

  const handleHexClicked = useCallback((q: number, r: number) => {
    if (!isMyTurn || phase !== 'place_tile') return;

    if (isValidPlacement(gameData.board.kite_owners, currentOrientation, q, r)) {
      onAction('place_tile', { anchor_q: q, anchor_r: r, orientation: currentOrientation });
      setHoverHex(null);
      return;
    }

    // Current orientation doesn't fit — try to find one that does
    for (let o = 0; o < NUM_ORIENTATIONS; o++) {
      if (isValidPlacement(gameData.board.kite_owners, o, q, r)) {
        setCurrentOrientation(o);
        // Don't auto-place — let the user see the preview first
        return;
      }
    }
  }, [isMyTurn, phase, gameData.board.kite_owners, currentOrientation, onAction]);

  // ── Drag from tray ──

  const handleTrayDragStart = useCallback(() => {
    if (!isMyTurn || phase !== 'place_tile') return;
    setIsDraggingFromTray(true);
  }, [isMyTurn, phase]);

  // Window-level pointer events for tray drag
  useEffect(() => {
    if (!isDraggingFromTray) return;

    const handlePointerMove = (e: PointerEvent) => {
      const board = boardRef.current;
      if (!board) return;
      const hex = board.screenToHex(e.clientX, e.clientY);
      if (hex) setHoverHex(hex);
    };

    const handlePointerUp = (e: PointerEvent) => {
      setIsDraggingFromTray(false);

      const board = boardRef.current;
      if (!board) return;
      const hex = board.screenToHex(e.clientX, e.clientY);
      if (!hex) return;

      if (isValidPlacement(kiteOwnersRef.current, currentOrientationRef.current, hex.q, hex.r)) {
        onAction('place_tile', {
          anchor_q: hex.q,
          anchor_r: hex.r,
          orientation: currentOrientationRef.current,
        });
        setHoverHex(null);
      }
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };
  }, [isDraggingFromTray, onAction]);

  // ── Ghost piece computation ──

  const ghostPiece: GhostPiece | null = useMemo(() => {
    if (!hoverHex || !isMyTurn || phase !== 'place_tile') return null;

    const valid = isValidPlacement(
      gameData.board.kite_owners,
      currentOrientation,
      hoverHex.q,
      hoverHex.r,
    );

    return {
      orientation: currentOrientation,
      anchorQ: hoverHex.q,
      anchorR: hoverHex.r,
      valid,
    };
  }, [hoverHex, isMyTurn, phase, gameData.board.kite_owners, currentOrientation]);

  // ── Scores ──

  const scores = useMemo(() => {
    const scoreMap: Record<string, number> = {};
    view.players.forEach(player => {
      scoreMap[player.player_id] = gameData.scores?.[player.player_id] || 0;
    });
    return scoreMap;
  }, [view.players, gameData.scores]);

  // Mobile status
  const getMobileStatus = (): string => {
    if (isGameOver) return t('game.status.gameOver');
    if (!isMyTurn) return t('game.status.opponentTurn');
    return t('game.status.tapToPlace');
  };

  return (
    <div className="flex flex-col md:flex-row h-full">
      {/* Board area */}
      <div className="flex-1 relative min-h-0">
        <EinsteinDojoBoard
          ref={boardRef}
          gameData={gameData}
          players={view.players}
          onHexClicked={handleHexClicked}
          onHoverHex={handleHoverHex}
          onHoverLeave={handleHoverLeave}
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
            onDragStart={handleTrayDragStart}
            isMyTurn={isMyTurn}
            isDragging={isDraggingFromTray}
            playerColor={playerColor}
            seatIndex={playerSeatIndex}
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
