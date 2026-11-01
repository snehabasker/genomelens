import { useEffect, useRef, useState } from 'react'
import { fmtMs } from './reduce'

interface Props { cursor: number | null; endT: number; setCursor: (t: number | null) => void }

export default function Playback({ cursor, endT, setCursor }: Props) {
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(4)
  const raf = useRef(0)
  const shown = cursor ?? endT

  useEffect(() => {
    if (!playing) return
    let last = performance.now()
    let pos = cursor === null || cursor >= endT ? 0 : cursor
    const tick = (now: number) => {
      pos += (now - last) * speed
      last = now
      if (pos >= endT) { setPlaying(false); setCursor(null); return }
      setCursor(pos)
      raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, speed, endT])

  return (
    <div className="playback">
      <button className="pb-btn" onClick={() => { if (!playing) setCursor(cursor === null || cursor >= endT ? 0 : cursor); setPlaying(!playing) }}
        aria-label={playing ? 'Pause' : 'Play'}>{playing ? '❚❚' : '▶'}</button>
      <input type="range" min={0} max={Math.max(endT, 1)} value={shown} aria-label="Scrub through the run"
        onChange={e => { setPlaying(false); const v = Number(e.target.value); setCursor(v >= endT ? null : v) }} />
      <span className="pb-time">{fmtMs(shown)} / {fmtMs(endT)}</span>
      <select value={speed} onChange={e => setSpeed(Number(e.target.value))} aria-label="Playback speed">
        <option value={1}>1×</option><option value={4}>4×</option><option value={10}>10×</option>
      </select>
    </div>
  )
}
