import { useEffect, useRef } from 'react'
import type { GenomeEvent } from './types'

const EVENT_COLORS: Record<GenomeEvent['type'], string> = {
  session_start: '#6366f1',
  session_complete: '#10b981',
  session_error: '#ef4444',
  agent_start: '#3b82f6',
  agent_progress: '#60a5fa',
  agent_done: '#10b981',
  agent_error: '#ef4444',
  sequence_loaded: '#10b981',
  helix_highlight: '#ff0066',
  variant_decoded: '#f59e0b',
  protein_impact: '#8b5cf6',
  drug_interactions: '#ec4899',
  literature_found: '#f97316',
  report_section: '#94a3b8',
}

function formatEvent(event: GenomeEvent): { text: string; color: string } {
  const color = EVENT_COLORS[event.type] ?? '#94a3b8'

  let text = ''
  switch (event.type) {
    case 'session_start':
      text = `▶ Analysis started: "${event.data.query}"`
      break
    case 'session_error':
      text = `✗ Session error: ${event.data.error}`
      break
    case 'agent_start':
      text = `[${event.agent}] ${event.data.message || 'Starting...'}`
      break
    case 'agent_progress':
      text = `  → ${event.data.message}`
      break
    case 'agent_done':
      text = `[${event.agent}] ✓ Complete`
      break
    case 'agent_error':
      text = `[${event.agent}] ✗ ${event.data.error}`
      break
    case 'sequence_loaded':
      text = `  Gene: ${event.data.gene} | Chr${event.data.chromosome}:${event.data.position} | Seq: ${event.data.sequence?.slice(0, 20)}...`
      break
    case 'helix_highlight':
      text = `  🔴 Mutation at position ${event.data.position}: ${event.data.ref} → ${event.data.alt} (${event.data.type})`
      break
    case 'variant_decoded':
      text = `  ✓ ${event.data.gene} | ${event.data.variant_type} | ${event.data.cdna_change || event.data.rs_id}`
      break
    case 'protein_impact':
      text = `  Protein: ${event.data.protein_name} | Impact: ${event.data.impact} | ${event.data.consequence}`
      break
    case 'drug_interactions':
      text = `  ${event.data.drug_count} drug interaction(s) found for ${event.data.gene}`
      break
    case 'literature_found':
      text = `  ClinVar: ${event.data.clinvar_significance || 'N/A'} | Papers: ${event.data.papers?.length || 0}`
      break
    case 'report_section':
      text = `  📄 Report section: "${event.data.title}"`
      break
    case 'session_complete':
      text = `■ Analysis complete — ${event.data.gene || ''} ${event.data.variant || ''}`
      break
    default: {
      const unknownEvent: never = event
      text = JSON.stringify(unknownEvent).slice(0, 60)
    }
  }

  return { text, color }
}

interface Props {
  events: GenomeEvent[]
}

export default function LiveStream({ events }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  return (
    <div className="live-stream">
      <div className="stream-header">
        <span className="stream-dot" />
        LIVE EVENT STREAM
      </div>
      <div className="stream-body">
        {events.length === 0 && (
          <div className="stream-empty">Waiting for analysis...</div>
        )}
        {events.map((event, idx) => {
          const { text, color } = formatEvent(event)
          return (
            <div key={idx} className="stream-line" style={{ borderLeftColor: color }}>
              <span className="stream-text" style={{ color }}>
                {text}
              </span>
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
