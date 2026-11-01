// Wire protocol. Every server event carries `t`: milliseconds since the run started.
// The UI is a pure function of (events, cursor) so any run can be replayed or scrubbed.

export type AgentId =
  | 'variant_decoder' | 'protein_impact' | 'pharmacogenomics' | 'literature_clinical' | 'synthesis'

export type AgentStatus = 'idle' | 'running' | 'done' | 'error'
export type RunStatus = 'idle' | 'running' | 'complete' | 'partial' | 'blocked' | 'fallback' | 'timeout' | 'crashed'
export type Confidence = 'high' | 'medium' | 'low'
export type WsStatus = 'disconnected' | 'connecting' | 'connected' | 'error'
export type ClaimStatus = 'pending' | 'supported' | 'partial' | 'unsupported' | 'n/a'

export interface RawEvent {
  type: string
  t: number
  agent?: AgentId | null
  data: Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any
}

export interface Mutation { type: string; ref: string; alt: string }

export interface ToolCall {
  t: number; ms: number; source: string; path: string; status: number
  cached: boolean; attempt: number; error: string | null; agent: AgentId | null
}
export interface LlmCall {
  t: number; ms: number; role: string; provider: string; model: string; cached: boolean
  ttft_ms: number; input_tokens: number; output_tokens: number; cost_usd: number; error?: string
  saved_usd?: number
}
export interface Evidence { id: string; source: string; title: string; text: string; url: string; quarantined: boolean }
export interface Guard {
  t: number; action: string; kind: string; message: string; snippet: string; suggestions?: string[]
  source?: string
}
export interface Claim { text: string; evidence_ids: string[]; kind: string; status: ClaimStatus; reason?: string }
export interface GroundingStats {
  total: number; supported: number; partial: number; unsupported: number
  grounded_rate: number | null; unsupported_rate: number | null
}
export interface ClaimsView {
  mode: string; summary: string; confidence: Confidence; limitations: string[]
  claims: Claim[]; verified: boolean; stats: GroundingStats | null
}
export interface Section { agent: AgentId; title: string; content: string; confidence?: Confidence; sources: string[] }
export interface AgentState { status: AgentStatus; message: string; startT: number | null; endT: number | null }
export interface Totals { tool_calls: number; cache_hits: number; retries: number; llm_calls: number
  input_tokens: number; output_tokens: number; cost_usd: number }

export interface RunConfig {
  provider: string
  features: Record<string, boolean>
  chaos: { kill: string[]; slow: string[]; malformed: string[]; poison: string; llm_down: boolean }
}

export interface RunView {
  query: string
  status: RunStatus
  config: RunConfig | null
  agents: Record<AgentId, AgentState>
  tools: ToolCall[]
  llm: LlmCall[]
  evidence: Evidence[]
  guards: Guard[]
  claims: ClaimsView | null
  sections: Section[]
  variant: { gene: string; chromosome: string; position: number | null; variant_type: string; cdna_change: string; rs_id: string } | null
  helix: { sequence: string; variantPosition: number | null; mutation: Mutation | null }
  totals: Totals
  degraded: Record<string, string>
  replayed: boolean
  savedUsd: number
  endT: number
  lastT: number
}

export interface PresetExample { query: string; label: string }
export interface PresetAttack { id: string; label: string; kind: string; query: string; blurb: string }
export interface PresetChaos { id: string; label: string; chaos: Partial<RunConfig['chaos']>; blurb: string }
export interface ServerConfig {
  models: { synthesis: string; judge: string; local: string }
  cloud_available: boolean; local_available: boolean
  budget: { daily_usd: number; spent_usd: number; exhausted: boolean }
  rate_limit: { runs: number; window_s: number }
  sources: string[]
  examples: PresetExample[]; attacks: PresetAttack[]; chaos: PresetChaos[]
}

export type ClientMessage =
  | { type: 'ping' }
  | { type: 'analyze'; query: string; provider: 'cloud' | 'local'; defenses: boolean; chaos?: Partial<RunConfig['chaos']> }

export const AGENT_ORDER: AgentId[] =
  ['variant_decoder', 'protein_impact', 'pharmacogenomics', 'literature_clinical', 'synthesis']
