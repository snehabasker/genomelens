import { useState, useCallback } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { useWebSocket } from './useWebSocket'
import DNAHelix from './DNAHelix'
import AgentNodes from './AgentNodes'
import LiveStream from './LiveStream'
import ReportBuilder from './ReportBuilder'
import type {
  AgentId, AgentState, GenomeEvent, HelixData, ReportSection, VariantData,
} from './types'

const EXAMPLE_QUERIES = [
  'rs1801133',
  'BRCA1 c.5266dupC',
  'rs334',
  'MTHFR c.677C>T',
  'TP53 c.817C>T',
]

const INITIAL_HELIX: HelixData = { sequence: '', variantPosition: null, mutation: null }

const INITIAL_AGENT_STATES: Record<AgentId, AgentState> = {
  variant_decoder: { status: 'idle', message: '' },
  protein_impact: { status: 'idle', message: '' },
  pharmacogenomics: { status: 'idle', message: '' },
  literature_clinical: { status: 'idle', message: '' },
}

export default function App() {
  const [query, setQuery] = useState<string>('')
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [events, setEvents] = useState<GenomeEvent[]>([])
  const [agentStates, setAgentStates] = useState<Record<AgentId, AgentState>>(INITIAL_AGENT_STATES)
  const [helixData, setHelixData] = useState<HelixData>(INITIAL_HELIX)
  const [reportSections, setReportSections] = useState<ReportSection[]>([])
  const [variantData, setVariantData] = useState<VariantData | null>(null)
  const [isComplete, setIsComplete] = useState(false)

  const handleEvent = useCallback((event: GenomeEvent) => {
    setEvents(prev => [...prev, event])

    switch (event.type) {
      case 'session_start':
        setIsAnalyzing(true)
        setIsComplete(false)
        setReportSections([])
        setVariantData(null)
        setHelixData(INITIAL_HELIX)
        setAgentStates({ ...INITIAL_AGENT_STATES })
        break

      case 'agent_start':
        setAgentStates(prev => ({
          ...prev,
          [event.agent]: { status: 'running', message: event.data.message || '' },
        }))
        break

      case 'agent_progress':
        setAgentStates(prev => ({
          ...prev,
          [event.agent]: { ...prev[event.agent], message: event.data.message || '' },
        }))
        break

      case 'agent_done':
        setAgentStates(prev => ({
          ...prev,
          [event.agent]: { status: 'done', message: 'Complete' },
        }))
        break

      case 'agent_error':
        setAgentStates(prev => ({
          ...prev,
          [event.agent]: { status: 'error', message: event.data.error || 'Error' },
        }))
        break

      case 'sequence_loaded':
        setHelixData(prev => ({
          ...prev,
          sequence: event.data.sequence || '',
          variantPosition: event.data.variant_position ?? null,
        }))
        break

      case 'helix_highlight':
        if (event.data.action === 'mutation_found') {
          setHelixData(prev => ({
            ...prev,
            mutation: { type: event.data.type, ref: event.data.ref, alt: event.data.alt },
            variantPosition: event.data.position ?? prev.variantPosition,
          }))
        }
        break

      case 'variant_decoded':
        setVariantData(event.data)
        break

      case 'report_section':
        setReportSections(prev => [...prev, {
          agent: event.agent,
          title: event.data.title,
          content: event.data.content,
          confidence: event.data.confidence,
          sources: event.data.sources || [],
        }])
        break

      case 'session_complete':
        setIsAnalyzing(false)
        setIsComplete(true)
        break

      case 'session_error':
        setIsAnalyzing(false)
        break

      default:
        break
    }
  }, [])

  const { status, send } = useWebSocket(handleEvent)

  const handleSubmit = (e: FormEvent | KeyboardEvent) => {
    e.preventDefault()
    if (!query.trim() || isAnalyzing) return
    setEvents([])
    send({ type: 'analyze', query: query.trim() })
  }

  return (
    <div className="app">
      {/* Top Bar */}
      <header className="topbar">
        <div className="topbar-logo">
          <span className="logo-helix">⬡</span>
          <span className="logo-text">GENOME LENS</span>
          <span className="logo-sub">Multi-Agent DNA Intelligence</span>
        </div>
        <div className="topbar-status">
          <span className={`ws-dot ws-${status}`} />
          <span className="ws-label">{status}</span>
        </div>
      </header>

      <div className="main-layout">
        {/* Left Panel — Input + Agents */}
        <aside className="left-panel">
          <form onSubmit={handleSubmit} className="query-form">
            <label className="query-label">Enter variant or gene</label>
            <textarea
              className="query-input"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="e.g. rs1801133  |  BRCA1 c.5266dupC  |  MTHFR c.677C>T"
              rows={3}
              disabled={isAnalyzing}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(e) } }}
            />
            <button
              type="submit"
              className={`analyze-btn ${isAnalyzing ? 'analyzing' : ''}`}
              disabled={isAnalyzing || !query.trim() || status !== 'connected'}
            >
              {isAnalyzing ? (
                <><span className="btn-spinner" /> Analyzing...</>
              ) : (
                '⚡ Analyze'
              )}
            </button>
          </form>

          <div className="examples">
            <div className="examples-label">Examples</div>
            <div className="examples-list">
              {EXAMPLE_QUERIES.map(q => (
                <button key={q} className="example-chip"
                  onClick={() => setQuery(q)} disabled={isAnalyzing}>
                  {q}
                </button>
              ))}
            </div>
          </div>

          <AgentNodes agentStates={agentStates} />

          <LiveStream events={events} />
        </aside>

        {/* Center Panel — DNA Helix */}
        <main className="center-panel">
          <div className="center-title">
            {variantData?.gene ? (
              <span>{variantData.gene} — {variantData.variant_type || 'Variant'}</span>
            ) : (
              <span>DNA Structure Viewer</span>
            )}
          </div>
          <DNAHelix
            sequence={helixData.sequence}
            variantPosition={helixData.variantPosition}
            mutation={helixData.mutation}
            isScanning={isAnalyzing}
          />
          {helixData.sequence && (
            <div className="seq-preview">
              <code>{helixData.sequence.slice(0, 40)}{helixData.sequence.length > 40 ? '…' : ''}</code>
            </div>
          )}
        </main>

        {/* Right Panel — Report */}
        <aside className="right-panel">
          <div className="report-title">
            Analysis Report
            {isAnalyzing && <span className="report-building">building…</span>}
          </div>
          <ReportBuilder
            sections={reportSections}
            variantData={variantData}
            isComplete={isComplete}
          />
        </aside>
      </div>
    </div>
  )
}
