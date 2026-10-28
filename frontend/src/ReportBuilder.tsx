import type { AgentId, Confidence, ReportSection, VariantData } from './types'

const CONFIDENCE_COLORS: Record<Confidence, string> = {
  high: '#10b981',
  medium: '#f59e0b',
  low: '#ef4444',
}

const AGENT_ICONS: Record<AgentId, string> = {
  variant_decoder: '🧬',
  protein_impact: '⚗️',
  pharmacogenomics: '💊',
  literature_clinical: '📚',
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function renderMarkdown(text: string): string {
  if (!text) return ''
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/\n/g, '<br/>')
}

interface Props {
  sections: ReportSection[]
  variantData: VariantData | null
  isComplete: boolean
}

export default function ReportBuilder({ sections, variantData, isComplete }: Props) {
  if (!sections.length && !variantData) {
    return (
      <div className="report-empty">
        <div className="report-empty-icon">🔬</div>
        <p>Analysis results will appear here as agents complete their work.</p>
      </div>
    )
  }

  return (
    <div className="report-builder">
      {/* Variant Header */}
      {variantData && (
        <div className="report-header-card">
          <div className="report-gene">{variantData.gene || 'Unknown Gene'}</div>
          <div className="report-meta">
            {variantData.chromosome && (
              <span className="meta-tag">Chr {variantData.chromosome}</span>
            )}
            {variantData.position && (
              <span className="meta-tag">Pos {variantData.position?.toLocaleString()}</span>
            )}
            {variantData.variant_type && (
              <span className="meta-tag variant-type">{variantData.variant_type}</span>
            )}
            {variantData.rs_id && (
              <span className="meta-tag rs-id">{variantData.rs_id}</span>
            )}
          </div>
          {variantData.cdna_change && (
            <div className="report-cdna">{variantData.cdna_change}</div>
          )}
        </div>
      )}

      {/* Sections */}
      {sections.map((section, idx) => (
        <div key={idx} className="report-section">
          <div className="section-header">
            <span className="section-icon">{AGENT_ICONS[section.agent] || '📄'}</span>
            <span className="section-title">{section.title}</span>
            {section.confidence && (
              <span className="section-confidence"
                style={{ color: CONFIDENCE_COLORS[section.confidence] }}>
                {section.confidence}
              </span>
            )}
          </div>
          <div className="section-content"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(section.content) }} />
          {section.sources && section.sources.length > 0 && (
            <div className="section-sources">
              Sources: {section.sources.join(' · ')}
            </div>
          )}
        </div>
      ))}

      {isComplete && (
        <div className="report-complete-badge">
          ✓ Analysis complete
        </div>
      )}
    </div>
  )
}
