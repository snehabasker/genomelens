import type { AgentId, AgentState } from './types'
import { fmtMs } from './reduce'

interface Node { id: AgentId; label: string; x: number; y: number; sub: string }

const NODES: Node[] = [
  { id: 'variant_decoder', label: 'Variant Decoder', x: 12, y: 78, sub: 'dbSNP · NCBI Gene' },
  { id: 'protein_impact', label: 'Protein Impact', x: 232, y: 8, sub: 'UniProt · Ensembl VEP' },
  { id: 'pharmacogenomics', label: 'Pharmacogenomics', x: 232, y: 78, sub: 'ClinPGx · DGIdb' },
  { id: 'literature_clinical', label: 'Literature & Clinical', x: 232, y: 148, sub: 'ClinVar · PubMed' },
  { id: 'synthesis', label: 'Synthesis + Verifier', x: 452, y: 78, sub: 'cited claims · grounding check' },
]
const EDGES: [AgentId, AgentId][] = [
  ['variant_decoder', 'protein_impact'], ['variant_decoder', 'pharmacogenomics'],
  ['variant_decoder', 'literature_clinical'], ['protein_impact', 'synthesis'],
  ['pharmacogenomics', 'synthesis'], ['literature_clinical', 'synthesis'],
]
const W = 168, H = 62
const byId = Object.fromEntries(NODES.map(n => [n.id, n])) as Record<AgentId, Node>

interface Props { agents: Record<AgentId, AgentState>; nowT: number; lastT: number; live: boolean }

export default function AgentGraph({ agents, nowT, lastT, live }: Props) {
  const clock = live ? Math.max(nowT, lastT) : lastT
  return (
    <svg className="agent-graph" viewBox="0 0 632 218" role="img" aria-label="Agent execution graph">
      {EDGES.map(([a, b]) => {
        const A = byId[a], B = byId[b]
        const x1 = A.x + W, y1 = A.y + H / 2, x2 = B.x, y2 = B.y + H / 2
        const mx = (x1 + x2) / 2
        const active = agents[b].status === 'running' || (agents[a].status === 'done' && agents[b].status === 'idle' && false)
        const lit = agents[b].startT !== null
        return (
          <path key={a + b} d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`}
            className={`edge ${lit ? 'lit' : ''} ${active ? 'flow' : ''}`} />
        )
      })}
      {NODES.map(n => {
        const s = agents[n.id]
        const dur = s.startT === null ? null : (s.endT ?? clock) - s.startT
        return (
          <g key={n.id} transform={`translate(${n.x},${n.y})`} className={`node st-${s.status}`}>
            <rect width={W} height={H} rx={10} />
            <circle cx={14} cy={16} r={4.5} className="dot" />
            <text x={26} y={20} className="n-title">{n.label}</text>
            <text x={12} y={37} className="n-sub">{s.status === 'idle' ? n.sub : (s.message || n.sub).slice(0, 30)}</text>
            <text x={12} y={53} className="n-time">
              {s.status === 'idle' ? '' : s.status === 'error' ? `failed · ${fmtMs(dur ?? 0)}` : fmtMs(dur ?? 0)}
              {s.status === 'running' ? ' …' : ''}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
