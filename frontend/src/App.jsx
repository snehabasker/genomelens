import { useState, useCallback } from 'react'
import { useWebSocket } from './useWebSocket'
import DNAHelix from './DNAHelix'
import AgentNodes from './AgentNodes'
import LiveStream from './LiveStream'
import ReportBuilder from './ReportBuilder'

const EXAMPLE_QUERIES = [
  'rs1801133',
  'BRCA1 c.5266dupC',
  'rs334',
  'MTHFR c.677C>T',
  'TP53 c.817C>T',
]

const INITIAL_AGENT_STATES = {
  variant_decoder: { status: 'idle', message: '' },
  protein_impact: { status: 'idle', message: '' },
  pharmacogenomics: { status: 'idle', message: '' },
  literature_clinical: { status: 'idle', message: '' },
}

export default function App() {
  const [query, setQuery] = useState('')
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [events, setEvents] = useState([])
  const [agentStates, setAgentStates] = useState(INITIAL_AGENT_STATES)
  const [helixData, setHelixData] = useState({ sequence: '', variantPosition: null, mutation: null })
  const [reportSections, setReportSections] = useState([])
  const [variantData, setVariantData] = useState(null)
  const [isComplete, setIsComplete] = useState(false)

  const handleEvent = useCallback((event) => {
    setEvents(prev => [...prev, event])
    const { type, agent, data } = event

    switch (type) {
      case 'session_start':
        setIsAnalyzing(true)
        setIsComplete(false)
        setReportSections([])
        setVariantData(null)
        setHelixData({ sequence: '', variantPosition: null, mutation: null })
        setAgentStates({ ...INITIAL_AGENT_STATES })
        break

      case 'agent_start':
        setAgentStates(prev => ({
          ...prev,
          [agent]: { status: 'running', message: data.message || '' },
        }))
        break

      case 'agent_progress':
        setAgentStates(prev => ({
          ...prev,
          [agent]: { ...prev[agent], message: data.message || '' },
        }))
        break

      case 'agent_done':
        setAgentStates(prev => ({
          ...prev,
          [agent]: { status: 'done', message: 'Complete' },
        }))
        break

      case 'agent_error':
        setAgentStates(prev => ({
          ...prev,
          [agent]: { status: 'error', message: data.error || 'Error' },
        }))
        break

      case 'sequence_loaded':
        setHelixData(prev => ({
          ...prev,
          sequence: data.sequence || '',
          variantPosition: data.variant_position ?? null,
        }))
        break

      case 'helix_highlight':
        if (data.action === 'mutation_found') {
          setHelixData(prev => ({
            ...prev,
            mutation: { type: data.type, ref: data.ref, alt: data.alt },
            variantPosition: data.position ?? prev.variantPosition,
          }))
        }
        break

      case 'variant_decoded':
        setVariantData(data)
        break

      case 'report_section':
        setReportSections(prev => [...prev, {
          agent: agent,
          title: data.title,
          content: data.content,
          confidence: data.confidence,
          sources: data.sources || [],
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

  const handleSubmit = (e) => {
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
