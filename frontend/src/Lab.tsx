import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import AgentGraph from './AgentGraph'
import DNAHelix from './DNAHelix'
import GuardLog from './GuardLog'
import MetricsBar from './MetricsBar'
import Playback from './Playback'
import Report from './Report'
import Timeline from './Timeline'
import type { RunHandle } from './useRun'
import type { PresetChaos, ServerConfig } from './types'

interface ShowcaseItem { id: string; title: string; blurb: string; query: string }

export default function Lab({ run, config }: { run: RunHandle; config: ServerConfig | null }) {
  const [query, setQuery] = useState('rs334')
  const [provider, setProvider] = useState<'cloud' | 'local'>('local')
  const [defenses, setDefenses] = useState(true)
  const [chaos, setChaos] = useState<PresetChaos | null>(null)
  const [showcase, setShowcase] = useState<ShowcaseItem[]>([])
  const { view, running, wsStatus } = run

  useEffect(() => {
    if (config) setProvider(config.local_available ? 'local' : 'cloud')
  }, [config])
  useEffect(() => {
    fetch('/api/showcase').then(r => r.json()).then(j => setShowcase(j.items || [])).catch(() => {})
  }, [])

  const submit = (e?: FormEvent) => {
    e?.preventDefault()
    if (!query.trim() || running) return
    run.start({ type: 'analyze', query, provider, defenses, chaos: chaos?.chaos })
  }
  const replay = async (id: string) => {
    const j = await fetch(`/api/showcase/${id}`).then(r => r.json())
    run.load(j.events)
    if (j.query) setQuery(j.query)
  }
  useEffect(() => {   // deep link: #lab&replay=sickle
    const m = window.location.hash.match(/replay=([\w-]+)/)
    if (m) replay(m[1]).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const finished = !running && run.events.length > 0
  const live = running && run.cursor === null
  const localOk = config?.local_available, cloudOk = config?.cloud_available

  return (
    <div className="lab">
      <aside className="lab-left">
        <form onSubmit={submit} className="card query">
          <label htmlFor="q" className="label">Variant, gene, or DNA</label>
          <textarea id="q" value={query} rows={2} onChange={e => setQuery(e.target.value)} disabled={running}
            placeholder="rs1801133 · BRCA1 c.5266dup · CYP2C19*2"
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) submit(e) }} />
          <div className="chips">
            {(config?.examples ?? []).map(x => (
              <button type="button" key={x.query} className="chip" disabled={running} onClick={() => setQuery(x.query)}
                title={x.label}>{x.query}</button>
            ))}
          </div>

          <div className="label">Model</div>
          <div className="seg" role="radiogroup" aria-label="Model provider">
            <button type="button" role="radio" aria-checked={provider === 'local'} className={provider === 'local' ? 'on' : ''}
              onClick={() => setProvider('local')} disabled={running}>
              🔒 Local {config ? (localOk ? <small>{config.models.local}</small> : <small>not running</small>) : null}</button>
            <button type="button" role="radio" aria-checked={provider === 'cloud'} className={provider === 'cloud' ? 'on' : ''}
              onClick={() => setProvider('cloud')} disabled={running}>
              ☁ Cloud {config ? (cloudOk ? <small>{config.models.synthesis}</small> : <small>no key</small>) : null}</button>
          </div>

          <label className="switch">
            <input type="checkbox" checked={defenses} onChange={e => setDefenses(e.target.checked)} disabled={running} />
            <span>Defences on</span>
            <small>{defenses ? 'guardrails · retries · caching · grounding' : 'original v0 pipeline'}</small>
          </label>

          <div className="label">Inject a fault</div>
          <div className="chips">
            {(config?.chaos ?? []).map(c => (
              <button type="button" key={c.id} className={`chip chaos ${chaos?.id === c.id ? 'on' : ''}`} disabled={running}
                onClick={() => setChaos(chaos?.id === c.id ? null : c)} title={c.blurb}>{c.label}</button>
            ))}
          </div>
          {chaos && <div className="hint">{chaos.blurb}</div>}

          <button className="go" type="submit" disabled={running || !query.trim() || wsStatus !== 'connected'}>
            {running ? <><span className="spin" /> Analysing…</> : wsStatus !== 'connected' ? 'Connecting…' : 'Analyse'}
          </button>
        </form>

        {showcase.length > 0 && (
          <div className="card">
            <div className="label">Instant replays <small className="muted">free · recorded runs</small></div>
            {showcase.map(s => (
              <button key={s.id} className="replay-row" onClick={() => replay(s.id)}>
                <b>{s.title}</b><span>{s.blurb}</span></button>
            ))}
          </div>
        )}
        <GuardLog guards={view.guards} onPick={q => setQuery(q)} />
      </aside>

      <main className="lab-main">
        <MetricsBar view={view} nowT={run.nowT} live={live} />
        <div className="card">
          <AgentGraph agents={view.agents} nowT={run.nowT} lastT={view.lastT} live={live} />
        </div>
        <div className="card">
          <div className="label">Timeline <small className="muted">every database and model call, as it happened</small></div>
          <Timeline view={view} nowT={run.nowT} live={live} />
        </div>
        {finished && <div className="card"><Playback cursor={run.cursor} endT={run.endT} setCursor={run.setCursor} /></div>}
        <div className="card helix">
          <DNAHelix sequence={view.helix.sequence} variantPosition={view.helix.variantPosition}
            mutation={view.helix.mutation} isScanning={running} />
          {!view.helix.sequence && view.variant?.gene && (
            <div className="muted helix-note">Genomic sequence context is shown for rsID inputs when Ensembl (GRCh38) is reachable.</div>
          )}
        </div>
      </main>

      <section className="lab-right">
        <div className="card"><Report view={view} /></div>
      </section>
    </div>
  )
}
