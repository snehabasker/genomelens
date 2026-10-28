// Types for the Genome Lens WebSocket protocol. They mirror the events emitted by
// backend/orchestrator.py and backend/agents/*.py.

export type AgentId =
  | 'variant_decoder'
  | 'protein_impact'
  | 'pharmacogenomics'
  | 'literature_clinical'

export type AgentStatus = 'idle' | 'running' | 'done' | 'error'
export type Confidence = 'high' | 'medium' | 'low'
export type WsStatus = 'disconnected' | 'connecting' | 'connected' | 'error'

export interface VariantData {
  gene: string
  chromosome: string
  position: number | null
  variant_type: string
  cdna_change: string
  rs_id: string
  ref_allele: string
  alt_allele: string
}

export interface SequenceLoadedData {
  gene: string
  chromosome: string
  position: number | null
  sequence: string
  variant_position: number | null
  ref_allele: string
  alt_allele: string
  gc_content?: number
  protein_preview?: string
}

export interface HelixHighlightData {
  action: string
  position: number | null
  ref: string
  alt: string
  type: string
}

export interface ProteinImpactData {
  protein_name: string
  accession: string
  protein_length: number
  affected_domain: string
  amino_acid_change: string
  hgvsp: string
  consequence: string
  impact: string
  sift_prediction: string
  polyphen_prediction: string
  domains: unknown[]
  url: string
}

export interface DrugRecord {
  drug: string
  interaction_type: string
  phenotype?: string
  level?: string
}

export interface DrugInteractionsData {
  gene: string
  rs_id: string
  drug_count: number
  drugs: DrugRecord[]
}

export interface Paper {
  title: string
  url: string
  authors: string
  year: string | number
  journal: string
}

export interface LiteratureFoundData {
  clinvar_significance: string
  clinvar_review_status: string
  clinvar_entries: unknown[]
  papers: Paper[]
}

export interface ReportSectionData {
  title: string
  content: string
  confidence?: Confidence
  sources?: string[]
}

type SessionEvent<T extends string, D> = { type: T; agent?: undefined; data: D }
type AgentEvent<T extends string, D> = { type: T; agent: AgentId; data: D }

/** Every event the server can stream, discriminated on `type`. */
export type GenomeEvent =
  | SessionEvent<'session_start', { query: string }>
  | SessionEvent<'session_complete', { gene: string; variant: string; rs_id: string }>
  | SessionEvent<'session_error', { error: string }>
  | AgentEvent<'agent_start', { message: string }>
  | AgentEvent<'agent_progress', { message: string }>
  | AgentEvent<'agent_done', Record<string, never>>
  | AgentEvent<'agent_error', { error: string }>
  | AgentEvent<'sequence_loaded', SequenceLoadedData>
  | AgentEvent<'helix_highlight', HelixHighlightData>
  | AgentEvent<'variant_decoded', VariantData>
  | AgentEvent<'protein_impact', ProteinImpactData>
  | AgentEvent<'drug_interactions', DrugInteractionsData>
  | AgentEvent<'literature_found', LiteratureFoundData>
  | AgentEvent<'report_section', ReportSectionData>

export type ClientMessage = { type: 'analyze'; query: string } | { type: 'ping' }

export interface AgentState {
  status: AgentStatus
  message: string
}

export interface Mutation {
  type: string
  ref: string
  alt: string
}

export interface HelixData {
  sequence: string
  variantPosition: number | null
  mutation: Mutation | null
}

export interface ReportSection extends ReportSectionData {
  agent: AgentId
  sources: string[]
}
