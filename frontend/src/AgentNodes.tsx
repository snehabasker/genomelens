import type { AgentId, AgentState, AgentStatus } from './types'

interface AgentInfo {
  id: AgentId
  label: string
  icon: string
  description: string
}

const AGENTS: AgentInfo[] = [
  {
    id: 'variant_decoder',
    label: 'Variant Decoder',
    icon: '🧬',
    description: 'Resolves coordinates, classifies mutation type',
  },
  {
    id: 'protein_impact',
    label: 'Protein Impact',
    icon: '⚗️',
    description: 'VEP predictions, domain analysis',
  },
  {
    id: 'pharmacogenomics',
    label: 'Pharmacogenomics',
    icon: '💊',
    description: 'Drug-gene interactions via PharmGKB',
  },
  {
    id: 'literature_clinical',
    label: 'Literature & Clinical',
    icon: '📚',
    description: 'ClinVar, PubMed + AI synthesis',
  },
]

const STATUS_CLASS: Record<AgentStatus, string> = {
  idle: 'agent-idle',
  running: 'agent-running',
  done: 'agent-done',
  error: 'agent-error',
}

interface Props {
  agentStates: Record<AgentId, AgentState>
}

export default function AgentNodes({ agentStates }: Props) {
  return (
    <div className="agent-nodes">
      {AGENTS.map((agent) => {
        const state: AgentState = agentStates[agent.id] ?? { status: 'idle', message: '' }
        const statusClass = STATUS_CLASS[state.status]
        return (
          <div key={agent.id} className={`agent-card ${statusClass}`}>
            <div className="agent-header">
              <span className="agent-icon">{agent.icon}</span>
              <div className="agent-title-block">
                <span className="agent-name">{agent.label}</span>
                <span className="agent-desc">{agent.description}</span>
              </div>
              <span className={`agent-status-dot dot-${state.status}`} />
            </div>
            {state.message && (
              <div className="agent-message">{state.message}</div>
            )}
          </div>
        )
      })}
    </div>
  )
}
