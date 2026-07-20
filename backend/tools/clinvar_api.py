import httpx

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


async def search_clinvar(gene: str, variant: str = "") -> list:
    """Search ClinVar for variants in a gene."""
    term = f"{gene}[gene]"
    if variant:
        term += f" AND {variant}"

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{BASE}/esearch.fcgi",
            params={"db": "clinvar", "term": term, "retmode": "json", "retmax": "5"},
        )
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []

        r2 = await client.get(
            f"{BASE}/esummary.fcgi",
            params={"db": "clinvar", "id": ",".join(ids), "retmode": "json"},
        )
        r2.raise_for_status()
        result = r2.json().get("result", {})

    entries = []
    for uid in ids:
        item = result.get(uid, {})
        if not item:
            continue
        clin_sig = item.get("clinical_significance", {})
        entries.append({
            "id": uid,
            "title": item.get("title", ""),
            "gene": item.get("gene_sort", gene),
            "clinical_significance": clin_sig.get("description", "") if isinstance(clin_sig, dict) else str(clin_sig),
            "review_status": item.get("review_status", ""),
            "last_evaluated": item.get("last_evaluated", ""),
            "variation_type": item.get("variation_type", ""),
            "url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{uid}/",
        })
    return entries


async def get_pathogenicity(rs_id: str) -> dict:
    """Get ClinVar pathogenicity for an rs ID."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{BASE}/esearch.fcgi",
            params={"db": "clinvar", "term": rs_id, "retmode": "json", "retmax": "1"},
        )
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return {"clinical_significance": "not found", "rs_id": rs_id}

        r2 = await client.get(
            f"{BASE}/esummary.fcgi",
            params={"db": "clinvar", "id": ids[0], "retmode": "json"},
        )
        r2.raise_for_status()
        result = r2.json().get("result", {})

    item = result.get(ids[0], {})
    clin_sig = item.get("clinical_significance", {})
    return {
        "rs_id": rs_id,
        "clinical_significance": clin_sig.get("description", "unknown") if isinstance(clin_sig, dict) else str(clin_sig),
        "review_status": item.get("review_status", ""),
        "title": item.get("title", ""),
        "url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{ids[0]}/",
    }
