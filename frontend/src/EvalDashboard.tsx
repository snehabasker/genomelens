import { useEffect, useState } from 'react'
import { fmtMs } from './reduce'
import type { RawEvent } from './types'

interface Failure { id: string; category: string; query: string; failed: string[] }
type Agg = Record<string, any> & { failures: Failure[]; by_category: Record<string, { n: number; pass_rate: number | null }> } // eslint-disable-line @typescript-eslint/no-explicit-any
interface Summary {
  generated: string; provider: string; model: string; dataset: { n: number }
  configs: Record<string, Agg>; order: string[]; labels: Record<string, string>
  cost_study?: { rows: { label: string; per_request_usd: number; per_1k_usd: number; note: string }[]; notes: string[] } | null
}

// rate metrics: [key, label, higher-is-better, what it measures]
const RATES: [string, string, boolean, string][] = [
  ['resolution_accuracy', 'Resolves the right gene', true, 'known variants, HGVS, gene symbols, aliases'],
  ['alias_accuracy', 'Understands common names', true, 'CYP2C19*2, “MTHFR C677T”, factor V Leiden'],
  ['attack_block_rate', 'Blocks injection / markup / advice bait', true, '16 attacks (6 written after the defences, as a held-out test); none may reach a lookup or a model'],
  ['malformed_safe_rate', 'Stops safely on garbage input', true, '13 malformed inputs, ≤3 wasted calls, no model'],
  ['poison_resist_rate', 'Resists poisoned PubMed abstracts', true, 'attacker text must not reach the report'],
  ['chaos_honest_rate', 'Handles outages honestly', true, 'detects and discloses the failed source'],
  ['grounded_rate', 'Claims judged fully supported', true, 'resolvable inputs. NOT like-for-like: v0 is judged against all evidence, v1 only against what each claim cites'],
  ['deterministic_fail_rate', 'Claims with a figure or class absent from the evidence', false, 'judge-independent and like-for-like. Lower is better'],
  ['paper_relevance_at3', 'Relevant papers in top 3', true, 'title/abstract mention the gene or rsID (all inputs)'],
]
const pct = (x: number | null | undefined) => (x === null || x === undefined ? '–' : `${Math.round(x * 100)}%`)

function Bars({ s }: { s: Summary }) {
  const ids = s.order
  return (
    <div className="bars">
      <div className="legend">{ids.map((c, i) => <span key={c}><i className={`sw ser-${i}`} />{s.labels[c] ?? c}</span>)}</div>
      {RATES.map(([k, label, hi, what]) => (
        <div key={k} className="bar-row">
          <div className="bar-label"><b>{label}</b><small>{what}</small></div>
          <div className="bar-stack">
            {ids.map((c, i) => {
              const v = s.configs[c]?.[k] as number | null
              return (
                <div key={c} className="bar-line">
                  <div className="bar-track"><div className={`bar-fill ser-${i}`} style={{ width: `${(v ?? 0) * 100}%` }} /></div>
                  <span className={`bar-val ${hi ? '' : 'lower'}`}>{pct(v)}</span>
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function EvalDashboard({ onReplay }: { onReplay: (events: RawEvent[], query: string) => void }) {
  const [s, setS] = useState<Summary | null>(null)
  const [err, setErr] = useState('')
  const [cfg, setCfg] = useState('')

  useEffect(() => {
    fetch('/api/eval').then(r => { if (!r.ok) throw new Error('no results yet'); return r.json() })
      .then((j: Summary) => { setS(j); setCfg(j.order[j.order.length - 1]) }).catch(e => setErr(String(e.message || e)))
  }, [])

  if (err) return <div className="card pad">No evaluation results found yet. Run <code>python eval/run_eval.py</code>.</div>
  if (!s) return <div className="card pad">Loading…</div>

  const fails = s.configs[cfg]?.failures ?? []
  const replay = async (f: Failure) => {
    const j = await fetch(`/api/eval/case/${cfg}/${f.id}`).then(r => r.json())
    onReplay(j.events, j.case.query)
  }
  const row = (label: string, f: (a: Agg) => string) => (
    <tr><th scope="row">{label}</th>{s.order.map(c => <td key={c}>{f(s.configs[c])}</td>)}</tr>
  )

  return (
    <div className="evalpage">
      <div className="atk-intro">
        <h2>Evaluation harness</h2>
        <p>{s.dataset.n} test queries across 8 groups, run through the real pipeline against the live public databases
          with <b>{s.model}</b>. Same dataset, same data sources, same model for every version; only the pipeline changes.
          Generated {s.generated}.</p>
      </div>

      <div className="card pad"><Bars s={s} /></div>

      <div className="card pad">
        <div className="label">Latency, load and cost</div>
        <table className="tbl">
          <thead><tr><th />{s.order.map(c => <th key={c}>{s.labels[c] ?? c}</th>)}</tr></thead>
          <tbody>
            {row('End-to-end p50 / p95', a => `${a.latency_p50_ms ? fmtMs(a.latency_p50_ms) : '–'} / ${a.latency_p95_ms ? fmtMs(a.latency_p95_ms) : '–'}`)}
            {row('Time to first token p50 / p95', a => `${a.ttft_p50_ms ? fmtMs(a.ttft_p50_ms) : '–'} / ${a.ttft_p95_ms ? fmtMs(a.ttft_p95_ms) : '–'}`)}
            {row('Mean tokens in / out (live model runs)', a => `${a.mean_input_tokens ?? '–'} / ${a.mean_output_tokens ?? '–'}`)}
            {row('Model calls per run (resolvable inputs)', a => String(a.llm_calls_per_run ?? '–'))}
            {row('Claims per run', a => String(a.claims_per_run ?? '–'))}
            {row('Database calls per run', a => String(a.tool_calls_per_run))}
            {row('Calls wasted on bad input', a => String(a.wasted_calls_on_bad_input))}
            {row('Retries performed', a => String(a.retries_total))}
            {row('HTTP cache hit rate (cold start)', a => pct(a.http_cache_hit_rate))}
            {row('Overall pass rate', a => pct(a.pass_rate))}
          </tbody>
        </table>
        {s.cost_study && (
          <>
            <div className="label mt">Cost per 1,000 requests <small className="muted">projected from measured token counts</small></div>
            <table className="tbl">
              <thead><tr><th>Scenario</th><th>Per request</th><th>Per 1,000</th></tr></thead>
              <tbody>{s.cost_study.rows.map(r => (
                <tr key={r.label}><th scope="row">{r.label}<small>{r.note}</small></th>
                  <td>${r.per_request_usd.toFixed(4)}</td><td>${r.per_1k_usd.toFixed(2)}</td></tr>))}</tbody>
            </table>
            {s.cost_study.notes.map((n, i) => <p key={i} className="muted note">{n}</p>)}
          </>
        )}
      </div>

      <div className="card pad">
        <div className="label">Failure log
          <span className="seg inline">{s.order.map(c => (
            <button key={c} className={cfg === c ? 'on' : ''} onClick={() => setCfg(c)}>{s.labels[c] ?? c} ({s.configs[c].failures.length})</button>))}
          </span></div>
        {fails.length === 0 && <p className="muted">No failing cases for this version.</p>}
        {fails.map(f => (
          <div key={f.id} className="fail">
            <code>{f.id}</code><span className="tag">{f.category}</span>
            <span className="fq">{f.query || '(empty)'}</span>
            <span className="why">{f.failed.join(', ')}</span>
            <button className="chip" onClick={() => replay(f)}>Replay ▶</button>
          </div>
        ))}
      </div>
    </div>
  )
}
