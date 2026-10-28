import { useRef, useState, useCallback, useEffect } from 'react'
import type { ClientMessage, GenomeEvent, WsStatus } from './types'

const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`

function isGenomeEvent(value: unknown): value is GenomeEvent {
  if (typeof value !== 'object' || value === null) return false
  const v = value as { type?: unknown; data?: unknown }
  return typeof v.type === 'string' && v.type !== 'pong' && typeof v.data === 'object' && v.data !== null
}

export function useWebSocket(onEvent: (event: GenomeEvent) => void) {
  const ws = useRef<WebSocket | null>(null)
  const [status, setStatus] = useState<WsStatus>('disconnected')
  const onEventRef = useRef(onEvent)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    onEventRef.current = onEvent
  }, [onEvent])

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN ||
        ws.current?.readyState === WebSocket.CONNECTING) return

    const socket = new WebSocket(WS_URL)
    ws.current = socket
    setStatus('connecting')

    socket.onopen = () => {
      if (ws.current !== socket) return
      setStatus('connected')
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current)
        reconnectTimer.current = null
      }
    }

    socket.onmessage = (e: MessageEvent<string>) => {
      if (ws.current !== socket) return
      try {
        const parsed: unknown = JSON.parse(e.data)
        if (isGenomeEvent(parsed)) onEventRef.current(parsed)
      } catch {
        // ignore malformed frames
      }
    }

    socket.onclose = () => {
      if (ws.current !== socket) return
      setStatus('disconnected')
      ws.current = null
      // Auto-reconnect after 3 seconds
      reconnectTimer.current = setTimeout(() => connect(), 3000)
    }

    socket.onerror = () => {
      if (ws.current !== socket) return
      setStatus('error')
    }
  }, [])

  const send = useCallback((data: ClientMessage) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(data))
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      ws.current?.close()
    }
  }, [connect])

  return { status, send, connect }
}
