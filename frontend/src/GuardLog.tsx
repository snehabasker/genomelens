import type { Guard } from './types'

const ICON: Record<string, string> = {
  blocked: '⛔', quarantined: '☣', fallback: '↩', retry: '⟳', normalized: '✎', cache_hit: '⚡',
  warn: '⚠', timeout: '⏱', error: '✕',
}
const TITLE: Record<string, string> = {
  blocked: 'Blocked', quarantined: 'Quarantined', fallback: 'Fallback', retry: 'Retry', normalized: 'Normalised',
  cache_hit: 'Cache hit', warn: 'Notice', timeout: 'Timeout', error: 'Error',
}
const TONE: Record<string, string> = {
  blocked: 'g-bad', quarantined: 'g-warn', fallback: 'g-info', retry: 'g-info', normalized: 'g-ok',
  cache_hit: 'g-ok', warn: 'g-warn', timeout: 'g-bad', error: 'g-bad',
}

export default function GuardLog({ guards, onPick }: { guards: Guard[]; onPick?: (q: string) => void }) {
  if (!guards.length) return null
  return (
    <div className="guards" role="log" aria-label="Defence log">
      {guards.map((g, i) => (
        <div key={i} className={`guard ${TONE[g.action] ?? 'g-info'}`}>
          <span className="g-icon" aria-hidden>{ICON[g.action] ?? '•'}</span>
          <div>
            <div className="g-head"><b>{TITLE[g.action] ?? g.action}</b><code>{g.kind}</code></div>
            <div className="g-msg">{g.message}</div>
            {g.snippet && <div className="g-snip">matched: <code>{g.snippet}</code></div>}
            {g.suggestions && onPick && (
              <div className="g-sug">Try: {g.suggestions.slice(0, 4).map(s => (
                <button key={s} className="chip" onClick={() => onPick(s)}>{s}</button>))}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
