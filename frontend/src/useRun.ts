import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { reduce } from './reduce'
import type { ClientMessage, RawEvent, RunView, WsStatus } from './types'

const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`

/** One WebSocket + the event list of the run it is streaming + a playback cursor. */
export function useRun() {
  const ws = useRef<WebSocket | null>(null)
  const retry = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [wsStatus, setWsStatus] = useState<WsStatus>('disconnected')
  const [events, setEvents] = useState<RawEvent[]>([])
  const [running, setRunning] = useState(false)
  const [cursor, setCursor] = useState<number | null>(null) // null = follow the live end
  const [nowT, setNowT] = useState(0)
  const wall0 = useRef(0)

  const connect = useCallback(() => {
    if (ws.current && ws.current.readyState <= WebSocket.OPEN) return
    const socket = new WebSocket(WS_URL)
    ws.current = socket
    setWsStatus('connecting')
    socket.onopen = () => ws.current === socket && setWsStatus('connected')
    socket.onerror = () => ws.current === socket && setWsStatus('error')
    socket.onclose = () => {
      if (ws.current !== socket) return
      setWsStatus('disconnected')
      ws.current = null
      retry.current = setTimeout(connect, 2500)
    }
    socket.onmessage = (m: MessageEvent<string>) => {
      if (ws.current !== socket) return
      let ev: RawEvent
      try { ev = JSON.parse(m.data) } catch { return }
      if (!ev || ev.type === 'pong' || typeof ev.data !== 'object') return
      setEvents(prev => {
        const t = typeof ev.t === 'number' ? ev.t : (prev.length ? prev[prev.length - 1].t : 0)
        return [...prev, { ...ev, t }]
      })
      if (ev.type === 'session_complete' || ev.type === 'session_error') setRunning(false)
    }
  }, [])

  useEffect(() => {
    connect()
    return () => { if (retry.current) clearTimeout(retry.current); ws.current?.close() }
  }, [connect])

  // wall-clock ticker so running agents' timers move between events
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => setNowT(Date.now() - wall0.current), 100)
    return () => clearInterval(id)
  }, [running])

  const start = useCallback((msg: Extract<ClientMessage, { type: 'analyze' }>) => {
    if (ws.current?.readyState !== WebSocket.OPEN) return false
    setEvents([]); setCursor(null); setRunning(true)
    wall0.current = Date.now(); setNowT(0)
    ws.current.send(JSON.stringify(msg))
    return true
  }, [])

  /** Load a finished run (showcase, history, eval case) for replay. */
  const load = useCallback((evs: RawEvent[]) => {
    setRunning(false); setEvents(evs); setCursor(null)   // open on the finished state; ▶ replays from 0
  }, [])

  const view: RunView = useMemo(() => reduce(events, cursor ?? Infinity), [events, cursor])
  const endT = events.length ? events[events.length - 1].t : 0
  return { wsStatus, events, view, running, cursor, setCursor, nowT, endT, start, load }
}
export type RunHandle = ReturnType<typeof useRun>
