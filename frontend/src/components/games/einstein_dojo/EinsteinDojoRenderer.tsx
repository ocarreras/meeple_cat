'use client';

import { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { PlayerView, EinsteinDojoGameData } from '@/lib/types';
import { useGameStore } from '@/stores/gameStore';
import { orientationInfo, orientationIndex, NUM_ORIENTATIONS, isValidPlacement, getValidMarkHexes, getResolvableConflicts } from '@/lib/einsteinPieces';
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
  const [selectedConflict, setSelectedConflict] = useState<string | null>(null);
  const [actionMode, setActionMode] = useState<'place_tile' | 'place_mark' | 'resolve_conflict'>('place_tile');
  const [selectedMark, setSelectedMark] = useState<string | null>(null);
  const [selectedResolve, setSelectedResolve] = useState<string | null>(null);

  const gameData = view.game_data as EinsteinDojoGameData;
  const gameOver = useGameStore((state) => state.gameOver);
  const isGameOver = view.status === 'finished' || gameOver !== null;

  const currentPlayerId = view.current_phase?.expected_actions?.[0]?.player_id;
  const viewerPlayer = view.players.find(p => p.player_id === view.viewer_id);
  const playerSeatIndex = viewerPlayer?.seat_index ?? 0;
  const playerColor = PLAYER_COLORS[playerSeatIndex % PLAYER_COLORS.length];

  // Main conflict
  const mainConflict = gameData.main_conflict;
  const chooseableConflicts = useMemo(() => {
    if (phase !== 'choose_main_conflict') return [];
    const hexes = view.current_phase?.metadata?.conflict_hexes;
    return Array.isArray(hexes) ? (hexes as string[]) : [];
  }, [phase, view.current_phase?.metadata?.conflict_hexes]);

  const handleConflictSelected = useCallback((hexKey: string) => {
    setSelectedConflict(hexKey);
  }, []);

  const handleConfirmConflict = useCallback(() => {
    if (selectedConflict) {
      onAction('choose_main_conflict', { hex: selectedConflict });
      setSelectedConflict(null);
    }
  }, [selectedConflict, onAction]);

  const handleMarkSelected = useCallback((hexKey: string) => {
    setSelectedMark(hexKey);
  }, []);

  const handleConfirmMark = useCallback(() => {
    if (selectedMark) {
      onAction('place_mark', { hex: selectedMark });
      setSelectedMark(null);
    }
  }, [selectedMark, onAction]);

  const handleResolveSelected = useCallback((hexKey: string) => {
    setSelectedResolve(hexKey);
  }, []);

  const handleConfirmResolve = useCallback(() => {
    if (selectedResolve) {
      onAction('resolve_conflict', { hex: selectedResolve });
      setSelectedResolve(null);
    }
  }, [selectedResolve, onAction]);

  const myTilesRemaining = view.viewer_id
    ? gameData.tiles_remaining[view.viewer_id] ?? 0
    : 0;

  const myMarksRemaining = view.viewer_id
    ? gameData.marks_remaining[view.viewer_id] ?? 0
    : 0;

  // Valid mark hexes (memoized)
  const validMarkHexes = useMemo(() => {
    if (!isMyTurn || phase !== 'player_turn' || actionMode !== 'place_mark') return new Set<string>();
    return getValidMarkHexes(gameData.board.kite_owners, gameData.board.hex_states, gameData.board.hex_marks);
  }, [isMyTurn, phase, actionMode, gameData.board.kite_owners, gameData.board.hex_states, gameData.board.hex_marks]);

  // Resolvable conflict hexes (memoized)
  const resolvableConflicts = useMemo(() => {
    if (!view.viewer_id) return new Set<string>();
    if (!isMyTurn) return new Set<string>();
    if (phase !== 'player_turn' && phase !== 'resolve_chain') return new Set<string>();
    return getResolvableConflicts(
      gameData.board.kite_owners,
      gameData.board.hex_states,
      gameData.board.hex_marks,
      gameData.board.hex_owners,
      view.viewer_id,
    );
  }, [isMyTurn, phase, view.viewer_id, gameData.board.kite_owners, gameData.board.hex_states, gameData.board.hex_marks, gameData.board.hex_owners]);

  const canResolve = resolvableConflicts.size > 0;

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
    setSelectedMark(null);
    setSelectedResolve(null);
    // Auto-switch to place_mark if no tiles left but marks remain
    if (myTilesRemaining <= 0 && myMarksRemaining > 0) {
      setActionMode('place_mark');
    } else {
      setActionMode('place_tile');
    }
  }, [view.turn_number, myTilesRemaining, myMarksRemaining]);

  // Auto-switch to resolve mode during resolve_chain phase
  useEffect(() => {
    if (phase === 'resolve_chain' && isMyTurn) {
      setActionMode('resolve_conflict');
      setSelectedResolve(null);
    }
  }, [phase, isMyTurn]);

  // Reset conflict selection when phase changes
  useEffect(() => {
    if (phase !== 'choose_main_conflict') {
      setSelectedConflict(null);
    }
  }, [phase]);

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
    if (!isMyTurn) return;

    // Resolve mode (player_turn or resolve_chain)
    if (actionMode === 'resolve_conflict' && (phase === 'player_turn' || phase === 'resolve_chain')) {
      const hexKey = `${q},${r}`;
      if (resolvableConflicts.has(hexKey)) {
        setSelectedResolve(hexKey);
      }
      return;
    }

    if (phase !== 'player_turn') return;

    if (actionMode === 'place_mark') {
      const hexKey = `${q},${r}`;
      if (validMarkHexes.has(hexKey)) {
        setSelectedMark(hexKey);
      }
      return;
    }

    // place_tile mode
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
  }, [isMyTurn, phase, actionMode, resolvableConflicts, validMarkHexes, gameData.board.kite_owners, currentOrientation, onAction]);

  // ── Drag from tray ──

  const handleTrayDragStart = useCallback(() => {
    if (!isMyTurn || phase !== 'player_turn' || actionMode !== 'place_tile') return;
    setIsDraggingFromTray(true);
  }, [isMyTurn, phase, actionMode]);

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
    if (!hoverHex || !isMyTurn || phase !== 'player_turn' || actionMode !== 'place_tile') return null;

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
  }, [hoverHex, isMyTurn, phase, actionMode, gameData.board.kite_owners, currentOrientation]);

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
    if (phase === 'choose_main_conflict') {
      return isMyTurn ? 'Choose the main conflict' : 'Opponent choosing main conflict...';
    }
    if (phase === 'resolve_chain') {
      return isMyTurn ? 'Resolve more conflicts or skip' : 'Opponent resolving conflicts...';
    }
    if (!isMyTurn) return t('game.status.opponentTurn');
    if (actionMode === 'resolve_conflict') return 'Tap a conflict hex to resolve';
    if (actionMode === 'place_mark') return 'Tap a hex to place mark';
    return t('game.status.tapToPlace');
  };

  const handleSkipResolve = useCallback(() => {
    onAction('skip_resolve', {});
  }, [onAction]);

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
          mainConflict={mainConflict}
          chooseableConflicts={chooseableConflicts}
          selectedConflict={selectedConflict}
          onConflictSelected={handleConflictSelected}
          onConfirmConflict={handleConfirmConflict}
          actionMode={actionMode}
          validMarkHexes={validMarkHexes}
          selectedMark={selectedMark}
          onMarkSelected={handleMarkSelected}
          onConfirmMark={handleConfirmMark}
          resolvableConflicts={resolvableConflicts}
          selectedResolve={selectedResolve}
          onResolveSelected={handleResolveSelected}
          onConfirmResolve={handleConfirmResolve}
        />
        {isGameOver && gameOver && (() => {
          const viewerIsWinner = view.viewer_id ? gameOver.winners.includes(view.viewer_id) : false;
          const winnerNames = gameOver.winners
            .map(id => view.players.find(p => p.player_id === id)?.display_name ?? id)
            .join(' & ');
          const reason = gameOver.reason;
          return (
            <div className="absolute inset-0 flex items-center justify-center bg-black/40">
              <div className="bg-white rounded-xl shadow-2xl p-6 max-w-sm mx-4 text-center">
                <h2 className="text-2xl font-bold mb-1">
                  {viewerIsWinner ? 'Victory!' : 'Defeat'}
                </h2>
                {reason === 'main_conflict_resolved' && (
                  <p className="text-sm text-purple-600 font-medium mb-3">
                    {viewerIsWinner
                      ? 'You resolved the main conflict!'
                      : `${winnerNames} resolved the main conflict`}
                  </p>
                )}
                {reason !== 'main_conflict_resolved' && (
                  <p className="text-sm text-gray-500 mb-3">{winnerNames} wins</p>
                )}
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
          );
        })()}
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
          {/* Action mode buttons */}
          {isMyTurn && phase === 'player_turn' && (
            <div className="bg-white rounded-lg border shadow-sm px-4 py-3">
              <div className="text-sm font-semibold mb-2">Action</div>
              <div className="flex gap-2">
                <button
                  onClick={() => { setActionMode('place_tile'); setSelectedMark(null); setSelectedResolve(null); }}
                  disabled={myTilesRemaining <= 0}
                  className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    actionMode === 'place_tile'
                      ? 'bg-blue-600 text-white'
                      : myTilesRemaining <= 0
                        ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                  }`}
                >
                  Tile ({myTilesRemaining})
                </button>
                <button
                  onClick={() => { setActionMode('place_mark'); setHoverHex(null); setSelectedResolve(null); }}
                  disabled={myMarksRemaining <= 0}
                  className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    actionMode === 'place_mark'
                      ? 'bg-blue-600 text-white'
                      : myMarksRemaining <= 0
                        ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                  }`}
                >
                  Mark ({myMarksRemaining})
                </button>
                <button
                  onClick={() => { setActionMode('resolve_conflict'); setHoverHex(null); setSelectedMark(null); }}
                  disabled={!canResolve}
                  className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    actionMode === 'resolve_conflict'
                      ? 'bg-purple-600 text-white'
                      : !canResolve
                        ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                  }`}
                >
                  Resolve
                </button>
              </div>
            </div>
          )}

          {/* Resolve chain panel */}
          {isMyTurn && phase === 'resolve_chain' && (
            <div className="bg-purple-50 rounded-lg border border-purple-200 shadow-sm px-4 py-3">
              <div className="text-sm font-semibold mb-2 text-purple-800">Resolve Chain</div>
              <p className="text-xs text-purple-600 mb-3">
                {canResolve
                  ? 'You can resolve more conflicts or skip.'
                  : 'No more conflicts to resolve.'}
              </p>
              <div className="flex gap-2">
                {canResolve && (
                  <span className="flex-1 text-center px-3 py-2 rounded-lg text-sm font-medium bg-purple-600 text-white">
                    Tap a conflict hex
                  </span>
                )}
                <button
                  onClick={handleSkipResolve}
                  className="flex-1 px-3 py-2 rounded-lg text-sm font-medium bg-gray-200 text-gray-700 hover:bg-gray-300 transition-colors"
                >
                  Skip
                </button>
              </div>
            </div>
          )}

          {actionMode === 'place_tile' && (
            <PieceTray
              currentOrientation={currentOrientation}
              tilesRemaining={myTilesRemaining}
              onRotate={handleRotate}
              onFlip={handleFlip}
              onDragStart={handleTrayDragStart}
              isMyTurn={isMyTurn}
              isDragging={isDraggingFromTray}
              playerColor={playerColor}
            />
          )}

          <ScoreBoard
            players={view.players}
            scores={scores}
            currentPlayerId={currentPlayerId ?? undefined}
            viewerId={view.viewer_id ?? undefined}
          />

          {/* Resources remaining for both players */}
          <div className="bg-white rounded-lg border shadow-sm px-4 py-3">
            <div className="text-sm font-semibold mb-2">Resources</div>
            {view.players.map(p => (
              <div key={p.player_id} className="flex items-center justify-between py-1">
                <div className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: PLAYER_COLORS[p.seat_index % PLAYER_COLORS.length] }}
                  />
                  <span className="text-sm">{p.display_name}</span>
                </div>
                <div className="flex gap-3 text-sm">
                  <span title="Tiles"><span className="text-gray-500">T:</span> <span className="font-bold">{gameData.tiles_remaining[p.player_id] ?? 0}</span></span>
                  <span title="Marks"><span className="text-gray-500">M:</span> <span className="font-bold">{gameData.marks_remaining[p.player_id] ?? 0}</span></span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
