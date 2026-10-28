import anthropic
from agents.base import BaseAgent
from tools.clinvar_api import search_clinvar, get_pathogenicity
from tools.pubmed_api import search_papers, fetch_abstract


class LiteratureClinicalAgent(BaseAgent):
    name = "literature_clinical"

    async def run(self, variant_data: dict):
        yield self.start("Searching clinical databases and literature...")

        gene = variant_data.get("gene", "")
        rs_id = variant_data.get("rs_id", "")
        variant_type = variant_data.get("variant_type", "")
        cdna_change = variant_data.get("cdna_change", "")

        clinvar_results = []
        pathogenicity_info = {}
        papers = []
        abstracts = []

        try:
            # ClinVar lookup
            if rs_id:
                yield self.progress("Checking ClinVar pathogenicity...")
                pathogenicity_info = await get_pathogenicity(rs_id)

            if gene and gene not in ("Unknown", "Raw Sequence", ""):
                yield self.progress(f"Searching ClinVar for {gene} variants...")
                variant_term = cdna_change if cdna_change else ""
                clinvar_results = await search_clinvar(gene, variant_term)

            # PubMed search
            search_term = f"{gene} {cdna_change or rs_id or variant_type}".strip()
            if not search_term or search_term == gene:
                search_term = f"{gene} variant pathogenicity"

            yield self.progress(f"Searching PubMed: '{search_term}'...")
            papers = await search_papers(search_term, max_results=4)

            # Fetch one abstract for synthesis
            if papers:
                abstract_text = await fetch_abstract(papers[0]["pmid"])
                if abstract_text:
                    abstracts.append(abstract_text[:1000])

            yield {"type": "literature_found", "agent": self.name, "data": {
                "clinvar_significance": pathogenicity_info.get("clinical_significance", ""),
                "clinvar_review_status": pathogenicity_info.get("review_status", ""),
                "clinvar_entries": clinvar_results[:3],
                "papers": papers,
            }}

            # Use Claude to synthesize findings
            yield self.progress("Synthesizing clinical interpretation with AI...")
            synthesis = await self._synthesize(
                gene=gene,
                rs_id=rs_id,
                cdna_change=cdna_change,
                variant_type=variant_type,
                pathogenicity=pathogenicity_info,
                clinvar_entries=clinvar_results[:3],
                papers=papers,
                abstracts=abstracts,
            )

            yield {"type": "report_section", "agent": self.name, "data": {
                "title": "Clinical Interpretation",
                "content": synthesis,
                "confidence": "high",
                "sources": ["ClinVar", "PubMed", "Claude AI"],
            }}

            # Also emit a literature section
            if papers:
                lit_lines = ["**Recent Literature:**\n"]
                for p in papers:
                    lit_lines.append(
                        f"- [{p['title'][:80]}...]({p['url']}) — {p['authors']} ({p['year']}, {p['journal']})"
                    )
                yield {"type": "report_section", "agent": self.name, "data": {
                    "title": "Literature References",
                    "content": "\n".join(lit_lines),
                    "confidence": "high",
                    "sources": ["PubMed"],
                }}

        except Exception as e:
            yield self.error(f"Literature search failed: {str(e)}")

        yield self.done()

    async def _synthesize(self, gene, rs_id, cdna_change, variant_type,
                          pathogenicity, clinvar_entries, papers, abstracts) -> str:
        variant_label = cdna_change or rs_id or variant_type or "this variant"
        clinvar_sig = pathogenicity.get("clinical_significance", "unknown")

        clinvar_summary = ""
        if clinvar_entries:
            clinvar_summary = "ClinVar entries:\n" + "\n".join(
                f"  - {e['title']}: {e['clinical_significance']}" for e in clinvar_entries
            )

        paper_summary = ""
        if papers:
            paper_summary = "Recent papers:\n" + "\n".join(
                f"  - {p['title']} ({p['year']})" for p in papers
            )

        abstract_summary = "\nKey abstract excerpt:\n" + abstracts[0] if abstracts else ""

        prompt = f"""You are a board-certified clinical genomics expert. Provide a concise, accurate clinical interpretation.

Gene: {gene}
Variant: {variant_label}
Variant Type: {variant_type}
ClinVar Significance: {clinvar_sig}

{clinvar_summary}

{paper_summary}
{abstract_summary}

Provide a clinical interpretation covering:
1. **Clinical Significance** — what this variant means for patient health
2. **Disease Associations** — known conditions linked to this variant/gene
3. **Penetrance & Expressivity** — if known
4. **Clinical Management** — surveillance, treatment, or genetic counseling implications
5. **Evidence Quality** — strength of evidence

Be concise (300-400 words). Use markdown formatting. Cite ClinVar or literature where relevant."""

        try:
            client = anthropic.AsyncAnthropic()
            response = await client.messages.create(
                model="claude-opus-4-8",
                max_tokens=4096,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": prompt}],
            )
            # Extract text content from response
            text_parts = [block.text for block in response.content if hasattr(block, "text")]
            return "\n".join(text_parts)
        except Exception as e:
            return (
                f"**Clinical Significance:** {clinvar_sig}\n\n"
                f"ClinVar records {len(clinvar_entries)} entries for {gene} variants.\n"
                f"PubMed returned {len(papers)} recent publications.\n\n"
                f"*(AI synthesis unavailable: {str(e)})*"
            )
