import asyncio

from agents.base import BaseAgent
from tools.sequence_tools import detect_input_type, parse_hgvs_cdna, translate, gc_content
from tools.ncbi_api import search_snp, search_gene
from tools.ensembl_api import get_gene_info, get_sequence


class VariantDecoderAgent(BaseAgent):
    name = "variant_decoder"

    async def fetch_context(self, vd: dict):
        """Cosmetic sequence context for the helix. Runs beside the analysis agents, never in front of
        them: a slow Ensembl must not delay the clinical result."""
        chromosome, position = vd.get("chromosome"), vd.get("position")
        if not (chromosome and position):
            return
        start, end = max(1, position - 30), position + 30
        yield self.progress(f"Fetching sequence context chr{chromosome}:{start}-{end}...")
        try:
            seq = await asyncio.wait_for(get_sequence(f"{chromosome}:{start}-{end}"), timeout=7)
        except Exception:
            seq = ""
        if not seq:
            yield self.progress("Sequence context unavailable (Ensembl); continuing without the helix view")
            return
        yield {"type": "sequence_loaded", "agent": self.name, "data": {
            "gene": vd.get("gene"), "chromosome": chromosome, "position": position, "sequence": seq,
            "variant_position": 30, "ref_allele": vd.get("ref_allele", ""), "alt_allele": vd.get("alt_allele", "")}}
        yield {"type": "helix_highlight", "agent": self.name, "data": {
            "action": "mutation_found", "position": 30, "ref": vd.get("ref_allele", ""),
            "alt": vd.get("alt_allele", ""), "type": vd.get("variant_type", "")}}

    def _strict(self) -> bool:
        return bool(self.rt and self.rt.features.early_exit)

    async def run(self, query: str):
        yield self.start("Parsing variant input...")

        parsed = detect_input_type(query)
        input_type = parsed.get("type", "search")

        gene = ""
        chromosome = ""
        position = None
        ref_allele = ""
        alt_allele = ""
        alt_alleles: list = []
        variant_type = "unknown"
        cdna_change = ""
        rs_id = ""

        try:
            if input_type == "rs_id":
                rs_id = parsed["rs_id"]
                yield self.progress(f"Resolving {rs_id} via NCBI...")
                snp = await search_snp(rs_id)
                if not snp:
                    yield self.progress(f"{rs_id} was not found in dbSNP")
                gene = snp.get("gene", "")
                chromosome = snp.get("chromosome", "")
                position = snp.get("position")
                ref_allele = snp.get("ref_allele", "")
                alt_alleles = snp.get("alt_alleles", [])
                alt_allele = alt_alleles[0] if alt_alleles else ""     # unknown stays unknown: never guess
                variant_type = snp.get("fxn_class", "SNP").replace("_", " ")
                cdna_change = snp.get("class", "snp")

            elif input_type == "hgvs":
                gene = parsed["gene"]
                cdna = parsed["cdna"]
                yield self.progress(f"Looking up {gene} in Ensembl...")
                gene_info = await get_gene_info(gene)
                if not gene_info and self._strict():
                    yield self.progress(f"{gene} is not a known human gene symbol")
                    gene = ""
                chromosome = gene_info.get("chromosome", "")
                hgvs_data = parse_hgvs_cdna(cdna)
                variant_type = hgvs_data.get("variant_type", "unknown")
                cdna_change = cdna
                # NOTE: a cDNA position cannot be turned into a genomic one by adding it to the gene
                # start (introns, strand, UTRs). The old code did exactly that and drew the wrong
                # locus on the helix, so no genomic position is claimed for c. inputs.
                position = None
                if hgvs_data.get("variant_type") == "substitution":
                    ref_allele = hgvs_data.get("ref", "")
                    alt_allele = hgvs_data.get("alt", "")
                elif hgvs_data.get("variant_type") in ("duplication", "insertion"):
                    ref_allele = "-"
                    alt_allele = hgvs_data.get("sequence", "N")
                elif hgvs_data.get("variant_type") == "deletion":
                    ref_allele = hgvs_data.get("sequence", "N") or "N"
                    alt_allele = "-"

            elif input_type == "raw_dna":
                seq = parsed["sequence"]
                yield self.progress("Analyzing raw DNA sequence...")
                gene = "Unknown"
                chromosome = "?"
                gc = gc_content(seq)
                protein = translate(seq[:300])
                yield {"type": "sequence_loaded", "agent": self.name, "data": {
                    "gene": "Raw Sequence",
                    "chromosome": "?",
                    "position": 0,
                    "sequence": seq[:60],
                    "gc_content": round(gc, 1),
                    "protein_preview": protein[:30],
                    "variant_position": 0,
                    "ref_allele": "",
                    "alt_allele": "",
                }}
                yield {"type": "variant_decoded", "agent": self.name, "data": {
                    "gene": "Raw Sequence", "chromosome": "", "position": None, "variant_type": "sequence",
                    "cdna_change": "", "rs_id": "", "ref_allele": "", "alt_allele": ""}}
                yield {"type": "report_section", "agent": self.name, "data": {
                    "title": "Sequence Analysis",
                    "content": (f"**Length:** {len(seq)} bases" + chr(10)
                                + f"**GC content:** {gc:.1f}%" + chr(10)
                                + f"**Translation (frame 1):** {protein[:60] or 'no ORF in frame 1'}" + chr(10)
                                + "Computed locally; the sequence was not sent to any external service."),
                    "confidence": "high", "sources": ["local computation"]}}
                yield self.done()
                return

            else:
                # Treat as gene name search
                gene = parsed.get("term", query)
                yield self.progress(f"Searching gene '{gene}'...")
                gene_info = await search_gene(gene)
                if not gene_info and self._strict():
                    yield self.progress(f"No human gene found for '{gene}'")
                    gene_info = {"gene": ""}
                gene = gene_info.get("gene", gene)
                chromosome = gene_info.get("chromosome", "")

            if not gene and self._strict():
                yield {"type": "variant_decoded", "agent": self.name, "data": {
                    "gene": "", "chromosome": chromosome, "position": position,
                    "variant_type": variant_type, "cdna_change": cdna_change, "rs_id": rs_id,
                    "ref_allele": ref_allele, "alt_allele": alt_allele}}
                yield self.done()
                return

            if not self._strict():
                # original behaviour: fetch the sequence inline, blocking every later stage
                # Fetch sequence context around variant
                sequence_preview = ""
                if chromosome and position:
                    start = max(1, position - 30)
                    end = position + 30
                    yield self.progress(f"Fetching sequence context chr{chromosome}:{start}-{end}...")
                    try:
                        region = f"{chromosome}:{start}-{end}"
                        sequence_preview = await get_sequence(region)
                    except Exception:
                        sequence_preview = "N" * 60

                variant_pos_in_preview = 30 if sequence_preview else 0

                yield {"type": "sequence_loaded", "agent": self.name, "data": {
                    "gene": gene,
                    "chromosome": chromosome,
                    "position": position,
                    "sequence": sequence_preview or ("N" * 60),
                    "variant_position": variant_pos_in_preview,
                    "ref_allele": ref_allele,
                    "alt_allele": alt_allele,
                }}

                if position:
                    yield {"type": "helix_highlight", "agent": self.name, "data": {
                        "action": "mutation_found",
                        "position": variant_pos_in_preview,
                        "ref": ref_allele,
                        "alt": alt_allele,
                        "type": variant_type,
                    }}

            yield {"type": "variant_decoded", "agent": self.name, "data": {
                "gene": gene,
                "chromosome": chromosome,
                "position": position,
                "variant_type": variant_type,
                "cdna_change": cdna_change,
                "rs_id": rs_id,
                "ref_allele": ref_allele,
                "alt_allele": alt_allele,
                "alt_alleles": alt_alleles,
            }}

            label = rs_id or f"{gene} {cdna_change}".strip()
            where = f"chromosome {chromosome}" + (f" position {position}" if position else "")
            alleles = (f"; alleles {ref_allele}>{'/'.join(alt_alleles)}" if ref_allele and alt_alleles else
                       f"; alleles {ref_allele}>{alt_allele}" if ref_allele and alt_allele else "")
            await self.evidence("dbSNP" if rs_id else "Ensembl", "Variant locus",
                                f"{label} is a {variant_type or 'variant'} in the gene {gene} at {where}{alleles}.")

        except Exception as e:
            yield self.error(f"Variant decoding failed: {str(e)}")

        yield self.done()
