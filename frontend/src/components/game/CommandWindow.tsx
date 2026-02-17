'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useGameStore } from '@/stores/gameStore';
import type { CommandWindowEntry } from '@/lib/types';

interface CommandWindowProps {
  onPanToTiles?: (tiles: string[]) => void;
}

export default function CommandWindow({ onPanToTiles }: CommandWindowProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const eventLog = useGameStore((state) => state.eventLog);
  const addEvents = useGameStore((state) => state.addEvents);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (expanded && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [eventLog.length, expanded]);

  const handleCommand = useCallback(
    (input: string) => {
      const trimmed = input.trim();
      if (!trimmed) return;

      if (trimmed === '/help') {
        addEvents([
          {
            id: `cmd-${Date.now()}`,
            timestamp: Date.now(),
            type: 'command_response',
            text: t('commandWindow.helpResponse'),
          },
        ]);
      } else {
        addEvents([
          {
            id: `cmd-${Date.now()}`,
            timestamp: Date.now(),
            type: 'command_response',
            text: t('commandWindow.unknownCommand'),
          },
        ]);
      }
    },
    [addEvents, t],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        handleCommand(inputValue);
        setInputValue('');
      }
    },
    [inputValue, handleCommand],
  );

  const handleFeatureClick = useCallback(
    (entry: CommandWindowEntry) => {
      if (entry.tiles && onPanToTiles) {
        onPanToTiles(entry.tiles);
      }
    },
    [onPanToTiles],
  );

  const latestEvent = eventLog[eventLog.length - 1];

  const renderEntry = (entry: CommandWindowEntry) => {
    if (entry.type === 'command_response') {
      return <span className="text-yellow-400">{entry.text}</span>;
    }

    if (entry.type === 'system') {
      return <span className="text-green-400 font-semibold">{entry.text}</span>;
    }

    // Scoring event: "[Name] scored X points on [featureType]"
    // Split into player name (colored) + rest, with clickable feature link
    const scoredIdx = entry.text.indexOf(' scored ');
    if (scoredIdx === -1) {
      return <span style={{ color: entry.playerColor }}>{entry.text}</span>;
    }

    const playerName = entry.text.slice(0, scoredIdx);
    const onIdx = entry.text.lastIndexOf(' on ');

    // For end-game points (no feature link)
    if (!entry.tiles || !entry.featureType || onIdx === -1) {
      return (
        <>
          <span style={{ color: entry.playerColor }}>{playerName}</span>
          <span className="text-gray-300">{entry.text.slice(scoredIdx)}</span>
        </>
      );
    }

    // Mid-game scoring with clickable feature
    const middle = entry.text.slice(scoredIdx, onIdx + 4); // " scored X points on "
    return (
      <>
        <span style={{ color: entry.playerColor }}>{playerName}</span>
        <span className="text-gray-300">{middle}</span>
        <button
          className="text-blue-400 hover:text-blue-300 underline"
          onClick={() => handleFeatureClick(entry)}
        >
          {entry.featureType}
        </button>
      </>
    );
  };

  // Collapsed bar
  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        className="w-full bg-gray-800 text-gray-200 px-3 py-1.5 flex items-center gap-2 text-sm hover:bg-gray-700 transition-colors"
      >
        <span className="text-gray-500 text-xs font-mono">{'>'}</span>
        <span className="flex-1 text-left truncate text-xs font-mono">
          {latestEvent ? latestEvent.text : t('commandWindow.placeholder')}
        </span>
        <svg
          className="w-4 h-4 text-gray-400 shrink-0"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
        </svg>
      </button>
    );
  }

  // Expanded panel
  return (
    <div className="w-full bg-gray-800 text-gray-200 flex flex-col" style={{ height: '200px' }}>
      {/* Header */}
      <button
        onClick={() => setExpanded(false)}
        className="flex items-center justify-between px-3 py-1 border-b border-gray-700 hover:bg-gray-700 transition-colors shrink-0"
      >
        <span className="text-xs font-medium text-gray-400">
          {t('commandWindow.title')}
        </span>
        <svg
          className="w-4 h-4 text-gray-400 rotate-180"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
        </svg>
      </button>

      {/* Scrollable log */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-3 py-1 space-y-0.5 font-mono text-xs"
      >
        {eventLog.length === 0 && (
          <div className="text-gray-500 italic py-2">{t('commandWindow.empty')}</div>
        )}
        {eventLog.map((entry) => (
          <div key={entry.id} className="leading-relaxed">
            {renderEntry(entry)}
          </div>
        ))}
      </div>

      {/* Input */}
      <div className="border-t border-gray-700 flex items-center px-3 py-1.5 shrink-0">
        <span className="text-gray-500 text-xs mr-2 font-mono">{'>'}</span>
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t('commandWindow.inputPlaceholder')}
          className="flex-1 bg-transparent text-gray-200 text-xs font-mono outline-none placeholder-gray-600"
        />
      </div>
    </div>
  );
}
