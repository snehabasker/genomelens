from agents.base import BaseAgent
from tools.pharmgkb_api import get_variant_drugs, get_gene_drugs, get_dgidb_interactions


class PharmacogenomicsAgent(BaseAgent):
    name = "pharmacogenomics"

    async def run(self, variant_data: dict):
        yield self.start("Scanning pharmacogenomics databases...")

        gene = variant_data.get("gene", "")
        rs_id = variant_data.get("rs_id", "")

        drug_records = []

        try:
            if rs_id:
                yield self.progress(f"Querying PharmGKB for {rs_id}...")
                variant_drugs = await self.safe(get_variant_drugs(rs_id), [])
                for r in variant_drugs:
                    for drug in r.get("drugs", []):
                        if drug:
                            drug_records.append({
                                "drug": drug,
                                "interaction_type": r.get("significance", "annotation"),
                                "level": r.get("level", ""),
                                "phenotype": r.get("phenotype", ""),
                                "source": "ClinPGx",
                            })

            if gene and gene not in ("Unknown", "Raw Sequence", ""):
                yield self.progress(f"Querying PharmGKB gene annotations for {gene}...")
                gene_drugs = await self.safe(get_gene_drugs(gene), [])
                seen = {d["drug"] for d in drug_records}
                for gd in gene_drugs:
                    if gd["drug"] not in seen:
                        drug_records.append({
                            "drug": gd["drug"],
                            "interaction_type": "pharmacogenomic",
                            "level": gd.get("level", ""),
                            "phenotype": gd.get("phenotype", ""),
                            "source": "ClinPGx",
                        })
                        seen.add(gd["drug"])

                yield self.progress(f"Querying DGIdb interactions for {gene}...")
                dgidb = await self.safe(get_dgidb_interactions(gene), [])
                seen2 = {d["drug"] for d in drug_records}
                for inter in dgidb:
                    drug = inter.get("drug", "")
                    if drug and drug not in seen2:
                        itype = inter.get("interaction_type", [])
                        drug_records.append({
                            "drug": drug,
                            "interaction_type": itype[0] if itype else "interaction",
                            "level": "N/A",
                            "phenotype": "",
                            "source": "DGIdb",
                        })
                        seen2.add(drug)

            yield {"type": "drug_interactions", "agent": self.name, "data": {
                "gene": gene,
                "rs_id": rs_id,
                "drug_count": len(drug_records),
                "drugs": drug_records[:15],
            }}

            for dr in drug_records[:6]:
                kind = dr["interaction_type"]
                lead = (f"{dr['source']} reports a drug-gene interaction between {dr['drug']} and {gene}"
                        if kind in ("interaction", "pharmacogenomic") else
                        f"{dr['source']} lists {dr['drug']} for {gene or rs_id}: {kind}")
                await self.evidence(dr["source"], f"Drug: {dr['drug']}", (
                    lead
                    + (f"; {dr['phenotype']}" if dr.get("phenotype") else "")
                    + (f" (evidence level {dr['level']})" if dr.get("level") not in ("", "N/A", None) else "") + "."))

            down = self.failed("ClinPGx", "DGIdb")
            if down and not drug_records:
                await self.evidence("ClinPGx", "Source unavailable",
                                    "Pharmacogenomic databases could not be reached, so no drug "
                                    "interaction information is available for this variant.")

            # Build report section
            if not drug_records and down:
                lines = [f"⚠ **Source unavailable:** {', '.join(down)} could not be reached, so this "
                         "section is empty because of an outage, not because no interactions exist."]
            elif drug_records:
                lines = [f"**{len(drug_records)} drug interaction(s) identified for {gene or rs_id}:**\n"]
                for dr in drug_records[:8]:
                    line = f"- **{dr['drug']}** — {dr['interaction_type']}"
                    if dr.get("phenotype"):
                        line += f" | {dr['phenotype']}"
                    if dr.get("level"):
                        line += f" (Level {dr['level']})"
                    line += f" [{dr['source']}]"
                    lines.append(line)
            else:
                lines = [f"No pharmacogenomic interactions currently catalogued for {gene or rs_id} in PharmGKB or DGIdb."]

            yield {"type": "report_section", "agent": self.name, "data": {
                "title": "Pharmacogenomics",
                "content": "\n".join(lines),
                "confidence": "high" if drug_records else "low",
                "degraded": bool(down),
                "sources": ["PharmGKB", "DGIdb"],
            }}

        except Exception as e:
            yield self.error(f"Pharmacogenomics search failed: {str(e)}")

        yield self.done()
