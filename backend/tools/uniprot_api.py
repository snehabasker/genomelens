from typing import Optional
import httpx

BASE = "https://rest.uniprot.org/uniprotkb"


async def get_protein_by_gene(gene: str) -> dict:
    """Fetch reviewed UniProt entry for a human gene."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{BASE}/search",
            params={
                "query": f"gene:{gene} AND organism_id:9606 AND reviewed:true",
                "format": "json",
                "fields": "accession,id,gene_names,protein_name,sequence,ft_domain,ft_region,ft_active_site,length",
                "size": "1",
            },
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    if not results:
        return {}

    entry = results[0]
    accession = entry.get("primaryAccession", "")
    protein_name = (
        entry.get("proteinDescription", {})
        .get("recommendedName", {})
        .get("fullName", {})
        .get("value", "")
    )
    seq_info = entry.get("sequence", {})
    domains = _extract_features(entry.get("features", []))

    return {
        "accession": accession,
        "protein_name": protein_name,
        "gene": gene,
        "length": seq_info.get("length", 0),
        "domains": domains,
        "url": f"https://www.uniprot.org/uniprotkb/{accession}",
    }


def _extract_features(features: list) -> list:
    result = []
    for feat in features:
        ftype = feat.get("type", "")
        if ftype not in ("Domain", "Region", "Active site", "Binding site"):
            continue
        loc = feat.get("location", {})
        start = loc.get("start", {}).get("value")
        end = loc.get("end", {}).get("value")
        desc = feat.get("description", "")
        result.append({"type": ftype, "start": start, "end": end, "description": desc})
    return result


def find_domain_at_position(domains: list, aa_position: int) -> Optional[str]:
    for d in domains:
        s = d.get("start")
        e = d.get("end")
        if s is not None and e is not None and s <= aa_position <= e:
            return d.get("description", d.get("type", "unknown domain"))
    return None
