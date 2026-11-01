import re
from agents.base import BaseAgent
from tools.uniprot_api import get_protein_by_gene
from tools.ensembl_api import vep_hgvs, vep_region


class ProteinImpactAgent(BaseAgent):
    name = "protein_impact"

    async def run(self, variant_data: dict):
        yield self.start("Fetching protein structure data...")

        gene = variant_data.get("gene", "")
        chromosome = variant_data.get("chromosome", "")
        position = variant_data.get("position")
        ref = variant_data.get("ref_allele", "")
        alt = variant_data.get("alt_allele", "")
        variant_type = variant_data.get("variant_type", "")
        cdna_change = variant_data.get("cdna_change", "")

        protein_info = {}
        vep_results = []

        try:
            if gene and gene not in ("Unknown", "Raw Sequence", ""):
                yield self.progress(f"Looking up {gene} in UniProt...")
                protein_info = await self.safe(get_protein_by_gene(gene), {})

            # Try VEP prediction
            if cdna_change.startswith("c.") and gene:       # an rsID's "snv" is not HGVS; it used to be sent as "HBB:snv"
                yield self.progress("Running variant effect prediction (VEP)...")
                hgvs = f"{gene}:{cdna_change}" if not cdna_change.startswith(gene) else cdna_change
                try:
                    vep_results = await self.safe(vep_hgvs(hgvs), [], timeout=14, source="Ensembl")
                except Exception:
                    vep_results = []

            if not vep_results and chromosome and position and ref and alt and alt != "-":
                # a multi-allelic SNP is asked about once per real alternate allele, never a guessed one
                for a in (variant_data.get("alt_alleles") or [alt])[:3]:
                    try:
                        found = await self.safe(vep_region(chromosome, position, ref, a), [], timeout=14, source="Ensembl")
                    except Exception:
                        found = []
                    vep_results += [{**v, "allele": a} for v in found]

            # Find the most impactful consequence
            best_vep = {}
            impact_order = {"HIGH": 0, "MODERATE": 1, "LOW": 2, "MODIFIER": 3}
            for v in vep_results:
                rank = impact_order.get(v.get("impact", "MODIFIER"), 3)
                best_rank = impact_order.get(best_vep.get("impact", "MODIFIER"), 3)
                if rank < best_rank:
                    best_vep = v

            # Determine domain hit
            domains = protein_info.get("domains", [])
            affected_domain = "N/A"
            aa_change = best_vep.get("amino_acids", "")
            hgvsp = best_vep.get("hgvsp", "")

            if hgvsp:
                m = re.search(r'p\.[A-Za-z]+(\d+)', hgvsp)
                if m:
                    aa_pos = int(m.group(1))
                    for d in domains:
                        s = d.get("start") or 0
                        e = d.get("end") or 0
                        if s <= aa_pos <= e:
                            affected_domain = d.get("description", d.get("type", "domain"))
                            break

            consequences = best_vep.get("consequence", [])
            consequence_str = ", ".join(consequences) if consequences else "unknown"

            sift = best_vep.get("sift", "")
            polyphen = best_vep.get("polyphen", "")

            yield {"type": "protein_impact", "agent": self.name, "data": {
                "protein_name": protein_info.get("protein_name", gene + " protein"),
                "accession": protein_info.get("accession", ""),
                "protein_length": protein_info.get("length", 0),
                "affected_domain": affected_domain,
                "amino_acid_change": aa_change or "N/A",
                "hgvsp": hgvsp or "N/A",
                "consequence": consequence_str,
                "impact": best_vep.get("impact", "unknown"),
                "sift_prediction": sift or "N/A",
                "polyphen_prediction": polyphen or "N/A",
                "domains": domains[:5],
                "url": protein_info.get("url", ""),
            }}

            if protein_info:
                dom = "; ".join(f"{d.get('description') or d.get('type')} ({d.get('start')}-{d.get('end')})"
                                for d in domains[:4])
                await self.evidence("UniProt", "Protein", (
                    f"{gene} encodes {protein_info.get('protein_name') or gene + ' protein'} "
                    f"(UniProt {protein_info.get('accession', '')}), {protein_info.get('length', 0)} amino acids."
                    + (f" Annotated regions: {dom}." if dom else "")), protein_info.get("url", ""))
            if best_vep:
                await self.evidence("Ensembl VEP", "Predicted effect", (
                    f"VEP predicts{(' for the ' + ref + '>' + best_vep['allele'] + ' allele') if best_vep.get('allele') else ''} {consequence_str} with {best_vep.get('impact', 'unknown')} impact"
                    + (f"; protein change {hgvsp} ({aa_change})" if hgvsp else "")
                    + (f"; SIFT: {sift}" if sift else "") + (f"; PolyPhen: {polyphen}" if polyphen else "")
                    + (f"; falls in domain: {affected_domain}" if affected_domain != "N/A" else "") + "."))
            if self.failed("UniProt"):
                await self.evidence("UniProt", "Source unavailable",
                                    "UniProt could not be reached, so protein domain information is unavailable.")
            if not best_vep and self.failed("Ensembl"):
                await self.evidence("Ensembl VEP", "Predicted effect",
                                    "Variant effect prediction was unavailable: Ensembl could not be reached.")

            # Report section
            impact_level = best_vep.get("impact", "unknown")
            content_lines = [
                f"**Protein:** {protein_info.get('protein_name', gene + ' protein')}",
                f"**Amino Acid Change:** {aa_change or 'N/A'} ({hgvsp or 'N/A'})",
                f"**Consequence:** {consequence_str}",
                f"**Impact Level:** {impact_level}",
                f"**Affected Domain:** {affected_domain}",
            ]
            if sift:
                content_lines.append(f"**SIFT:** {sift}")
            if polyphen:
                content_lines.append(f"**PolyPhen-2:** {polyphen}")

            yield {"type": "report_section", "agent": self.name, "data": {
                "title": "Protein Impact Analysis",
                "content": "\n".join(content_lines),
                "confidence": "high" if vep_results else "medium",
                "sources": ["UniProt", "Ensembl VEP"],
            }}

        except Exception as e:
            yield self.error(f"Protein impact analysis failed: {str(e)}")

        yield self.done()
