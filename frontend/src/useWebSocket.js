import { useRef, useState, useCallback, useEffect } from 'react'

const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`

export function useWebSocket(onEvent) {
  const ws = useRef(null)
  const [status, setStatus] = useState('disconnected')
  const onEventRef = useRef(onEvent)
  const reconnectTimer = useRef(null)

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

    socket.onmessage = (e) => {
      if (ws.current !== socket) return
      try {
        const event = JSON.parse(e.data)
        onEventRef.current(event)
      } catch (_) {}
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

  const send = useCallback((data) => {
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
