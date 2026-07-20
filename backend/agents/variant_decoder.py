from agents.base import BaseAgent
from tools.sequence_tools import detect_input_type, parse_hgvs_cdna, translate, gc_content
from tools.ncbi_api import search_snp, search_gene
from tools.ensembl_api import get_gene_info, get_sequence


class VariantDecoderAgent(BaseAgent):
    name = "variant_decoder"

    async def run(self, query: str):
        yield self.start("Parsing variant input...")

        parsed = detect_input_type(query)
        input_type = parsed.get("type", "search")

        gene = ""
        chromosome = ""
        position = None
        ref_allele = ""
        alt_allele = ""
        variant_type = "unknown"
        cdna_change = ""
        rs_id = ""

        try:
            if input_type == "rs_id":
                rs_id = parsed["rs_id"]
                yield self.progress(f"Resolving {rs_id} via NCBI...")
                snp = await search_snp(rs_id)
                gene = snp.get("gene", "")
                chromosome = snp.get("chromosome", "")
                position = snp.get("position")
                alleles = snp.get("alleles", "A/G")
                parts = alleles.split("/")
                ref_allele = parts[0] if parts else "A"
                alt_allele = parts[1] if len(parts) > 1 else "G"
                variant_type = snp.get("fxn_class", "SNP").replace("_", " ")
                cdna_change = snp.get("class", "snp")

            elif input_type == "hgvs":
                gene = parsed["gene"]
                cdna = parsed["cdna"]
                yield self.progress(f"Looking up {gene} in Ensembl...")
                gene_info = await get_gene_info(gene)
                chromosome = gene_info.get("chromosome", "")
                hgvs_data = parse_hgvs_cdna(cdna)
                variant_type = hgvs_data.get("variant_type", "unknown")
                cdna_change = cdna
                position = gene_info.get("start", 0) + hgvs_data.get("position", 0)
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
                yield self.done()
                return

            else:
                # Treat as gene name search
                gene = parsed.get("term", query)
                yield self.progress(f"Searching gene '{gene}'...")
                gene_info = await search_gene(gene)
                gene = gene_info.get("gene", gene)
                chromosome = gene_info.get("chromosome", "")

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
            }}

        except Exception as e:
            yield self.error(f"Variant decoding failed: {str(e)}")

        yield self.done()
