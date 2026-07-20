import { useEffect, useRef } from 'react'

const EVENT_COLORS = {
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

function formatEvent(event) {
  const { type, agent, data } = event
  const color = EVENT_COLORS[type] || '#94a3b8'

  let text = ''
  switch (type) {
    case 'session_start':
      text = `▶ Analysis started: "${data.query}"`
      break
    case 'agent_start':
      text = `[${agent}] ${data.message || 'Starting...'}`
      break
    case 'agent_progress':
      text = `  → ${data.message}`
      break
    case 'agent_done':
      text = `[${agent}] ✓ Complete`
      break
    case 'agent_error':
      text = `[${agent}] ✗ ${data.error}`
      break
    case 'sequence_loaded':
      text = `  Gene: ${data.gene} | Chr${data.chromosome}:${data.position} | Seq: ${data.sequence?.slice(0, 20)}...`
      break
    case 'helix_highlight':
      text = `  🔴 Mutation at position ${data.position}: ${data.ref} → ${data.alt} (${data.type})`
      break
    case 'variant_decoded':
      text = `  ✓ ${data.gene} | ${data.variant_type} | ${data.cdna_change || data.rs_id}`
      break
    case 'protein_impact':
      text = `  Protein: ${data.protein_name} | Impact: ${data.impact} | ${data.consequence}`
      break
    case 'drug_interactions':
      text = `  ${data.drug_count} drug interaction(s) found for ${data.gene}`
      break
    case 'literature_found':
      text = `  ClinVar: ${data.clinvar_significance || 'N/A'} | Papers: ${data.papers?.length || 0}`
      break
    case 'report_section':
      text = `  📄 Report section: "${data.title}"`
      break
    case 'session_complete':
      text = `■ Analysis complete — ${data.gene || ''} ${data.variant || ''}`
      break
    default:
      text = `${type}: ${JSON.stringify(data).slice(0, 60)}`
  }

  return { text, color }
}

export default function LiveStream({ events }) {
  const bottomRef = useRef(null)

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
