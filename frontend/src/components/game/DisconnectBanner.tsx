'use client';

import { useEffect, useState } from 'react';
import { useGameStore, type DisconnectNotification } from '@/stores/gameStore';

function CountdownTimer({ startTime, gracePeriod }: { startTime: number; gracePeriod: number }) {
  const [remaining, setRemaining] = useState(gracePeriod);

  useEffect(() => {
    const interval = setInterval(() => {
      const elapsed = (Date.now() - startTime) / 1000;
      const left = Math.max(0, gracePeriod - elapsed);
      setRemaining(Math.ceil(left));
      if (left <= 0) clearInterval(interval);
    }, 500);
    return () => clearInterval(interval);
  }, [startTime, gracePeriod]);

  return <span className="font-mono font-bold">{remaining}s</span>;
}

function NotificationItem({ notification, playerName }: { notification: DisconnectNotification; playerName: string }) {
  if (notification.type === 'disconnected') {
    return (
      <div className="flex items-center justify-between gap-3 bg-yellow-50 border border-yellow-300 text-yellow-800 px-4 py-2 rounded-lg text-sm">
        <span>
          <span className="font-semibold">{playerName}</span> disconnected.
          {notification.gracePeriod != null && (
            <>
              {' '}They have{' '}
              <CountdownTimer startTime={notification.timestamp} gracePeriod={notification.gracePeriod} />
              {' '}to reconnect.
            </>
          )}
        </span>
      </div>
    );
  }

  if (notification.type === 'reconnected') {
    return (
      <div className="flex items-center gap-3 bg-green-50 border border-green-300 text-green-800 px-4 py-2 rounded-lg text-sm">
        <span className="font-semibold">{playerName}</span> reconnected.
      </div>
    );
  }

  if (notification.type === 'forfeited') {
    return (
      <div className="flex items-center gap-3 bg-red-50 border border-red-300 text-red-800 px-4 py-2 rounded-lg text-sm">
        <span className="font-semibold">{playerName}</span> was forfeited due to disconnect.
      </div>
    );
  }

  return null;
}

export default function DisconnectBanner() {
  const notifications = useGameStore((state) => state.disconnectNotifications);
  const view = useGameStore((state) => state.view);

  if (notifications.length === 0) return null;

  const getPlayerName = (playerId: string) => {
    const player = view?.players.find((p) => p.player_id === playerId);
    return player?.display_name ?? 'A player';
  };

  return (
    <div className="flex flex-col gap-1 px-3 py-1">
      {notifications.map((n) => (
        <NotificationItem
          key={`${n.playerId}-${n.type}`}
          notification={n}
          playerName={getPlayerName(n.playerId)}
        />
      ))}
    </div>
  );
}
