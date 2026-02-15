'use client';

import { useTranslation } from 'react-i18next';

interface ConnectionStatusProps {
  connected: boolean;
  error: string | null;
}

export default function ConnectionStatus({ connected, error }: ConnectionStatusProps) {
  const { t } = useTranslation();

  return (
    <div className="flex items-center gap-2 text-sm">
      <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`} />
      <span className={connected ? 'text-green-700' : 'text-red-700'}>
        {connected ? t('game.connected') : t('game.disconnected')}
      </span>
      {error && (
        <span className="text-red-600 ml-2">
          {error}
        </span>
      )}
    </div>
  );
}
