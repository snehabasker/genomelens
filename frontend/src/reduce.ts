import type { AgentId, AgentState, Claim, RawEvent, RunStatus, RunView } from './types'

const idle = (): AgentState => ({ status: 'idle', message: '', startT: null, endT: null })

export function emptyView(): RunView {
  return {
    query: '', status: 'idle', config: null,
    agents: {
      variant_decoder: idle(), protein_impact: idle(), pharmacogenomics: idle(),
      literature_clinical: idle(), synthesis: idle(),
    },
    tools: [], llm: [], evidence: [], guards: [], claims: null, sections: [], variant: null,
    helix: { sequence: '', variantPosition: null, mutation: null },
    totals: { tool_calls: 0, cache_hits: 0, retries: 0, llm_calls: 0, input_tokens: 0, output_tokens: 0, cost_usd: 0 },
    degraded: {}, replayed: false, savedUsd: 0, endT: 0, lastT: 0,
  }
}

/** Fold the event list (up to time `upTo`) into everything the UI shows. Pure and cheap. */
export function reduce(events: RawEvent[], upTo = Infinity): RunView {
  const v = emptyView()
  for (const e of events) {
    if (e.t > upTo) break
    v.lastT = Math.max(v.lastT, e.t)
    const d = e.data
    const a = e.agent as AgentId | null | undefined
    switch (e.type) {
      case 'session_start':
        v.query = d.query; v.config = d.config; v.status = 'running'; break
      case 'agent_start':
        if (a) v.agents[a] = { status: 'running', message: d.message, startT: e.t, endT: null }
        break
      case 'agent_progress':
        if (a) v.agents[a] = { ...v.agents[a], message: d.message }
        break
      case 'agent_done':
        if (a) v.agents[a] = { ...v.agents[a], status: v.agents[a].status === 'error' ? 'error' : 'done', endT: e.t }
        break
      case 'agent_error':
        if (a) v.agents[a] = { ...v.agents[a], status: 'error', message: d.error, endT: e.t }
        break
      case 'tool_call':
        v.tools.push({ t: e.t, ms: d.ms, source: d.source, path: d.path, status: d.status, cached: d.cached,
          attempt: d.attempt, error: d.error, agent: a ?? null })
        v.totals.tool_calls += 1
        v.totals.cache_hits += d.cached ? 1 : 0
        v.totals.retries += d.attempt > 1 ? 1 : 0
        break
      case 'llm_call':
        v.llm.push({ t: e.t, ms: d.ms, role: d.role, provider: d.provider, model: d.model, cached: !!d.cached,
          ttft_ms: d.ttft_ms ?? 0, input_tokens: d.input_tokens ?? 0, output_tokens: d.output_tokens ?? 0,
          cost_usd: d.cost_usd ?? 0, error: d.error, saved_usd: d.saved_usd })
        v.totals.llm_calls += 1
        v.totals.input_tokens += d.input_tokens ?? 0
        v.totals.output_tokens += d.output_tokens ?? 0
        v.totals.cost_usd += d.cost_usd ?? 0
        break
      case 'evidence':
        v.evidence.push(d as RunView['evidence'][number]); break
      case 'guard':
        v.guards.push({ t: e.t, action: d.action, kind: d.kind, message: d.message, snippet: d.snippet ?? '',
          suggestions: d.suggestions, source: d.source })
        break
      case 'sequence_loaded':
        v.helix = { ...v.helix, sequence: d.sequence || '', variantPosition: d.variant_position ?? null }; break
      case 'helix_highlight':
        if (d.action === 'mutation_found')
          v.helix = { ...v.helix, mutation: { type: d.type, ref: d.ref, alt: d.alt }, variantPosition: d.position ?? v.helix.variantPosition }
        break
      case 'variant_decoded':
        v.variant = d as RunView['variant']; break
      case 'report_section':
        if (a) v.sections.push({ agent: a, title: d.title, content: d.content, confidence: d.confidence, sources: d.sources || [] })
        break
      case 'claims':
      case 'claims_verified':
        v.claims = {
          mode: d.mode, summary: d.summary, confidence: d.confidence, limitations: d.limitations || [],
          claims: (d.claims as Claim[]).map(c => ({ ...c, status: c.status ?? 'pending' })),
          verified: e.type === 'claims_verified', stats: d.stats ?? null,
        }
        break
      case 'session_complete':
        v.status = d.status as RunStatus
        v.degraded = d.degraded || {}
        v.replayed = !!d.replayed
        v.savedUsd = d.saved_usd || 0
        v.endT = e.t
        break
      case 'session_error':
        v.status = 'crashed'
        v.guards.push({ t: e.t, action: 'error', kind: d.kind || 'error', message: d.error, snippet: '' })
        break
    }
  }
  return v
}

export const fmtMs = (ms: number) => (ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`)
export const fmtUsd = (u: number) => (u === 0 ? '$0' : u < 0.01 ? `$${u.toFixed(4)}` : `$${u.toFixed(3)}`)
