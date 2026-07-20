from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class AnalysisRequest(BaseModel):
    variant: str
    session_id: Optional[str] = None


class ReportSection(BaseModel):
    agent: str
    title: str
    content: str
    confidence: Optional[str] = None
    sources: List[str] = []


class FinalReport(BaseModel):
    variant: str
    gene: Optional[str] = None
    variant_type: Optional[str] = None
    clinical_significance: Optional[str] = None
    sections: List[ReportSection] = []
    summary: Optional[str] = None


# WebSocket event shapes (sent as JSON to frontend)
# {"type": "agent_start", "agent": "variant_decoder", "data": {"message": "..."}}
# {"type": "sequence_loaded", "data": {"gene": "BRCA1", "chromosome": "17", ...}}
# {"type": "helix_highlight", "data": {"action": "mutation_found", "position": 25, ...}}
# {"type": "variant_decoded", "data": {...}}
# {"type": "protein_impact", "data": {...}}
# {"type": "drug_interactions", "data": {...}}
# {"type": "literature_found", "data": {...}}
# {"type": "report_section", "data": {"agent": "...", "title": "...", "content": "..."}}
# {"type": "agent_done", "agent": "..."}
# {"type": "session_complete", "data": {...}}
# {"type": "session_error", "data": {"error": "..."}}
