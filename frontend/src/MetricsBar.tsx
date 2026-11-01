import { fmtMs, fmtUsd } from './reduce'
import type { RunView } from './types'

export default function MetricsBar({ view, nowT, live }: { view: RunView; nowT: number; live: boolean }) {
  const t = live ? Math.max(nowT, view.lastT) : view.endT || view.lastT
  const synth = view.llm.find(l => l.role === 'synthesis' && !l.error)
  const hosts = new Set(view.tools.map(x => x.source))
  const provider = view.config?.provider ?? 'cloud'
  const llmReal = view.llm.filter(l => !l.cached && !l.error).length
  const privacy =
    provider === 'local'
      ? { cls: 'priv-local', text: `Local model · 0 LLM API calls · ${hosts.size} public database${hosts.size === 1 ? '' : 's'} contacted (identifiers only)` }
      : provider === 'extractive'
        ? { cls: 'priv-local', text: 'No model used · summary compiled from database records' }
        : { cls: 'priv-cloud', text: `Cloud model · ${llmReal} LLM API call${llmReal === 1 ? '' : 's'} (evidence text sent)` }
  return (
    <div className="metrics">
      <div className="m"><span>Time</span><b>{fmtMs(t)}</b></div>
      <div className="m"><span>TTFT</span><b>{synth && synth.ttft_ms ? fmtMs(synth.ttft_ms) : '–'}</b></div>
      <div className="m"><span>DB calls</span><b>{view.totals.tool_calls}</b><em>{view.totals.cache_hits} cached · {view.totals.retries} retries</em></div>
      <div className="m"><span>Model calls</span><b>{view.totals.llm_calls}</b><em>{view.llm.filter(l => l.cached).length} cached</em></div>
      <div className="m"><span>Tokens</span><b>{view.totals.input_tokens + view.totals.output_tokens || '–'}</b>
        <em>{view.totals.input_tokens} in · {view.totals.output_tokens} out</em></div>
      <div className="m"><span>Cost</span><b>{fmtUsd(view.totals.cost_usd)}</b>{view.savedUsd > 0 && <em>saved {fmtUsd(view.savedUsd)}</em>}</div>
      {view.status !== 'idle' && <div className={`privacy ${privacy.cls}`}>{privacy.text}</div>}
    </div>
  )
}
