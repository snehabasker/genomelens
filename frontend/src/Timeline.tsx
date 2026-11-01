import { useState } from 'react'
import { AGENT_ORDER, type AgentId, type LlmCall, type RunView, type ToolCall } from './types'
import { fmtMs } from './reduce'

const LABEL: Record<AgentId, string> = {
  variant_decoder: 'Decoder', protein_impact: 'Protein', pharmacogenomics: 'Pharma',
  literature_clinical: 'Literature', synthesis: 'Synthesis',
}
type Bar = { kind: 'tool' | 'llm'; start: number; ms: number; lane: AgentId; tool?: ToolCall; llm?: LlmCall }

export default function Timeline({ view, nowT, live }: { view: RunView; nowT: number; live: boolean }) {
  const [hover, setHover] = useState<Bar | null>(null)
  const clock = live ? Math.max(nowT, view.lastT) : view.lastT
  const span = Math.max(2000, clock * 1.04, view.endT)
  const bars: Bar[] = [
    ...view.tools.map(t => ({ kind: 'tool' as const, start: Math.max(0, t.t - t.ms), ms: t.ms, lane: (t.agent ?? 'variant_decoder') as AgentId, tool: t })),
    ...view.llm.map(l => ({ kind: 'llm' as const, start: Math.max(0, l.t - l.ms), ms: l.ms, lane: 'synthesis' as AgentId, llm: l })),
  ]
  const L = 78, R = 10, LANE = 28, TOP = 6, W = 620
  const x = (t: number) => L + (t / span) * (W - L - R)
  const ticks = Array.from({ length: 5 }, (_, i) => (span / 4) * i)

  return (
    <div className="timeline">
      <svg viewBox={`0 0 ${W} ${TOP + AGENT_ORDER.length * LANE + 22}`} role="img" aria-label="Timeline of agent activity and tool calls">
        {ticks.map(t => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={TOP} y2={TOP + AGENT_ORDER.length * LANE} className="grid" />
            <text x={x(t)} y={TOP + AGENT_ORDER.length * LANE + 14} className="axis" textAnchor="middle">{fmtMs(t)}</text>
          </g>
        ))}
        {AGENT_ORDER.map((a, i) => {
          const s = view.agents[a]
          const y = TOP + i * LANE
          return (
            <g key={a}>
              <text x={L - 8} y={y + LANE / 2 + 4} className="lane-label" textAnchor="end">{LABEL[a]}</text>
              {s.startT !== null && (
                <rect x={x(s.startT)} y={y + 3} height={LANE - 6} rx={4} className={`span span-${s.status}`}
                  width={Math.max(2, x(s.endT ?? clock) - x(s.startT))} />
              )}
            </g>
          )
        })}
        {bars.map((b, i) => {
          const y = TOP + AGENT_ORDER.indexOf(b.lane) * LANE
          const bad = b.kind === 'tool' ? !!b.tool!.error || b.tool!.status >= 400 : !!b.llm!.error
          const cached = b.kind === 'tool' ? b.tool!.cached : b.llm!.cached
          const cls = bad ? 'bar-bad' : b.kind === 'llm' ? 'bar-llm' : cached ? 'bar-cached' : 'bar-ok'
          return (
            <rect key={i} x={x(b.start)} y={y + 8} height={LANE - 16} rx={2} width={Math.max(3, x(b.start + b.ms) - x(b.start))}
              className={cls} onMouseEnter={() => setHover(b)} onMouseLeave={() => setHover(null)} />
          )
        })}
      </svg>
      <div className="tl-legend">
        <span><i className="sw bar-ok" />live request</span>
        <span><i className="sw bar-cached" />cache hit</span>
        <span><i className="sw bar-llm" />model call</span>
        <span><i className="sw bar-bad" />failed ✕</span>
      </div>
      <div className="tl-hover" aria-live="polite">
        {hover?.tool && <>
          <b>{hover.tool.source}</b> {hover.tool.path} · {hover.tool.status || 'no response'} · {fmtMs(hover.tool.ms)}
          {hover.tool.attempt > 1 && ` · attempt ${hover.tool.attempt}`}{hover.tool.cached && ' · cached'}
          {hover.tool.error && <span className="bad"> · {hover.tool.error}</span>}
        </>}
        {hover?.llm && <>
          <b>{hover.llm.role}</b> · {hover.llm.model} · {hover.llm.cached ? 'cached' : `TTFT ${fmtMs(hover.llm.ttft_ms)} · total ${fmtMs(hover.llm.ms)}`}
          {' · '}{hover.llm.input_tokens}→{hover.llm.output_tokens} tok{hover.llm.error && <span className="bad"> · {hover.llm.error}</span>}
        </>}
        {!hover && <span className="muted">Hover a bar for details. Retries and failures show as separate bars.</span>}
      </div>
    </div>
  )
}
