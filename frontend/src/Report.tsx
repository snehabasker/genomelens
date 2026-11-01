import { useState } from 'react'
import type { Claim, ClaimStatus, RunView } from './types'

const STATUS: Record<ClaimStatus, { icon: string; label: string }> = {
  supported: { icon: '✓', label: 'Supported by cited evidence' },
  partial: { icon: '◐', label: 'Partly supported' },
  unsupported: { icon: '✕', label: 'Not supported by the evidence' },
  pending: { icon: '…', label: 'Verifying' },
  'n/a': { icon: '·', label: '' },
}

function escapeHtml(t: string) {
  return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
function md(text: string) {
  return escapeHtml(text || '')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\[(.+?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer noopener">$1</a>')
    .replace(/\n/g, '<br/>')
}

function Grounding({ view }: { view: RunView }) {
  const c = view.claims
  if (!c) return null
  const s = c.stats
  const total = c.claims.filter(x => x.status !== 'n/a').length
  const seg = (n: number) => (total ? (n / total) * 100 : 0)
  const cnt = (st: ClaimStatus) => c.claims.filter(x => x.status === st).length
  return (
    <div className="grounding">
      <div className="g-title">
        <b>{c.verified && s ? `${s.supported}/${s.total} claims grounded` : `Verifying ${total} claims…`}</b>
        <span className="muted">{c.mode === 'llm' ? 'AI-written, citation-checked' : c.mode === 'extractive' ? 'compiled from records, no AI' : 'free text, sentence-checked'}</span>
      </div>
      <div className="g-bar" role="img" aria-label={`${cnt('supported')} supported, ${cnt('partial')} partial, ${cnt('unsupported')} unsupported`}>
        <i className="seg-ok" style={{ width: `${seg(cnt('supported'))}%` }} />
        <i className="seg-part" style={{ width: `${seg(cnt('partial'))}%` }} />
        <i className="seg-bad" style={{ width: `${seg(cnt('unsupported'))}%` }} />
        <i className="seg-pend" style={{ width: `${seg(cnt('pending'))}%` }} />
      </div>
    </div>
  )
}

export default function Report({ view }: { view: RunView }) {
  const [focus, setFocus] = useState<string | null>(null)
  const [showEv, setShowEv] = useState(false)
  const c = view.claims
  const down = Object.keys(view.degraded)

  if (!view.variant && !c && !view.sections.length) {
    return <div className="report-empty"><div className="big">🔬</div>
      <p>Results appear here as the agents finish. Every statement will carry a citation chip you can click.</p></div>
  }
  const byId = Object.fromEntries(view.evidence.map(e => [e.id, e]))
  const other = view.sections.filter(s => s.agent !== 'synthesis')

  return (
    <div className="report">
      {view.variant?.gene && view.variant.gene !== 'Raw Sequence' && (
        <div className="v-card">
          <div className="v-gene">{view.variant.gene}</div>
          <div className="v-tags">
            {view.variant.rs_id && <span className="tag">{view.variant.rs_id}</span>}
            {view.variant.cdna_change && !view.variant.rs_id && <span className="tag">{view.variant.cdna_change}</span>}
            {view.variant.chromosome && <span className="tag">chr {view.variant.chromosome}</span>}
            {view.variant.position && <span className="tag">pos {view.variant.position.toLocaleString()}</span>}
            {view.variant.variant_type && <span className="tag t-type">{view.variant.variant_type}</span>}
          </div>
        </div>
      )}

      {down.length > 0 && (
        <div className="degraded" role="alert">
          <b>Partial report.</b> {down.join(', ')} could not be reached. Anything those sources would have said is
          missing, not “absent”.
        </div>
      )}

      {c && (
        <section className="claims">
          <Grounding view={view} />
          {c.summary && <p className="summary">{c.summary}</p>}
          <ol>
            {c.claims.map((cl: Claim, i) => {
              const st = STATUS[cl.status]
              return (
                <li key={i} className={`claim st-${cl.status.replace('/', '')} ${focus && cl.evidence_ids.includes(focus) ? 'hl' : ''}`}>
                  <span className="c-icon" title={st.label} aria-label={st.label}>{st.icon}</span>
                  <div>
                    <span className="c-text">{cl.text}</span>{' '}
                    {cl.evidence_ids.map(id => (
                      <button key={id} className={`cite ${byId[id]?.quarantined ? 'cite-q' : ''} ${!byId[id] ? 'cite-x' : ''}`}
                        onMouseEnter={() => setFocus(id)} onMouseLeave={() => setFocus(null)}
                        onClick={() => { setShowEv(true); setFocus(id) }}
                        title={byId[id] ? `${byId[id].source}: ${byId[id].text.slice(0, 160)}` : 'No such evidence'}>{id}</button>
                    ))}
                    {cl.status === 'unsupported' && cl.reason && <div className="c-why">{cl.reason}</div>}
                    {cl.status === 'partial' && cl.reason && <div className="c-why warn">{cl.reason}</div>}
                  </div>
                </li>
              )
            })}
          </ol>
          {c.limitations.length > 0 && (
            <div className="limits"><b>Limitations</b><ul>{c.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul></div>
          )}
        </section>
      )}

      {other.map((s, i) => (
        <details key={i} className="sec" open={s.agent === 'pharmacogenomics' || s.agent === 'protein_impact'}>
          <summary>{s.title}{s.confidence && <em className={`conf conf-${s.confidence}`}>{s.confidence}</em>}</summary>
          <div className="sec-body" dangerouslySetInnerHTML={{ __html: md(s.content) }} />
          {s.sources.length > 0 && <div className="sec-src">Sources: {s.sources.join(' · ')}</div>}
        </details>
      ))}

      {view.evidence.length > 0 && (
        <div className="evidence">
          <button className="ev-toggle" onClick={() => setShowEv(!showEv)}>
            {showEv ? '▾' : '▸'} Evidence ({view.evidence.length} items{view.evidence.some(e => e.quarantined) ? ', 1+ quarantined' : ''})
          </button>
          {showEv && view.evidence.map(e => (
            <div key={e.id} className={`ev ${focus === e.id ? 'hl' : ''} ${e.quarantined ? 'ev-q' : ''}`}>
              <code className="ev-id">{e.id}</code>
              <div>
                <div className="ev-src">{e.source}{e.quarantined && <span className="q-badge">quarantined</span>}</div>
                <div className="ev-text">{e.url && !e.quarantined ? <a href={e.url} target="_blank" rel="noreferrer noopener">{e.text}</a> : e.text}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
