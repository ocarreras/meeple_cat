'use client';

import { useEffect, useRef, useCallback } from 'react';
import type { ServerMessage, ActionMessage } from '@/lib/types';

export interface UseWebSocketOptions {
  matchId: string;
  token: string;
  onMessage: (message: ServerMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
}

interface WebSocketReturn {
  sendAction: (action: ActionMessage) => void;
  sendPing: () => void;
  close: () => void;
}

const MIN_RECONNECT_DELAY = 1000; // 1 second
const MAX_RECONNECT_DELAY = 30000; // 30 seconds

export function useWebSocket(options: UseWebSocketOptions): WebSocketReturn {
  const { matchId, token, onMessage, onConnect, onDisconnect } = options;

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectDelayRef = useRef(MIN_RECONNECT_DELAY);
  const isManualCloseRef = useRef(false);
  const isMountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!isMountedRef.current) {
      return;
    }

    // Clear any existing connection
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    // Build WebSocket URL - detect protocol from window location
    const protocol = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = typeof window !== 'undefined' ? window.location.host : 'localhost:3000';
    const wsUrl = `${protocol}//${host}/ws/game/${matchId}?token=${token}`;

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      if (!isMountedRef.current) {
        ws.close();
        return;
      }

      console.log('WebSocket connected');

      // Reset reconnect delay on successful connection
      reconnectDelayRef.current = MIN_RECONNECT_DELAY;

      if (onConnect) {
        onConnect();
      }
    };

    ws.onmessage = (event) => {
      if (!isMountedRef.current) {
        return;
      }

      try {
        const message = JSON.parse(event.data) as ServerMessage;
        onMessage(message);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.onclose = () => {
      if (!isMountedRef.current) {
        return;
      }

      console.log('WebSocket disconnected');
      wsRef.current = null;

      if (onDisconnect) {
        onDisconnect();
      }

      // Attempt to reconnect if not manually closed
      if (!isManualCloseRef.current && isMountedRef.current) {
        const delay = reconnectDelayRef.current;
        console.log(`Reconnecting in ${delay}ms...`);

        reconnectTimeoutRef.current = setTimeout(() => {
          if (isMountedRef.current) {
            // Exponential backoff with max delay
            reconnectDelayRef.current = Math.min(
              reconnectDelayRef.current * 2,
              MAX_RECONNECT_DELAY
            );
            connect();
          }
        }, delay);
      }
    };

    wsRef.current = ws;
  }, [matchId, token, onMessage, onConnect, onDisconnect]);

  // Connect on mount
  useEffect(() => {
    isMountedRef.current = true;
    isManualCloseRef.current = false;
    connect();

    return () => {
      isMountedRef.current = false;

      // Clear reconnect timeout
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }

      // Close WebSocket
      if (wsRef.current) {
        isManualCloseRef.current = true;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  const sendAction = useCallback((action: ActionMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: 'action',
          payload: action,
        })
      );
    } else {
      console.warn('WebSocket not connected, cannot send action');
    }
  }, []);

  const sendPing = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: 'ping',
        })
      );
    }
  }, []);

  const close = useCallback(() => {
    isManualCloseRef.current = true;

    // Clear reconnect timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Close WebSocket
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  return {
    sendAction,
    sendPing,
    close,
  };
}
