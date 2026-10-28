import httpx

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _classification(item: dict) -> dict:
    """ClinVar esummary now reports germline_classification; clinical_significance is the legacy name."""
    c = item.get("germline_classification") or item.get("clinical_significance") or {}
    return c if isinstance(c, dict) else {"description": str(c)}


def _has_dbsnp_id(item: dict, rs_number: str) -> bool:
    for vs in item.get("variation_set") or []:
        for x in vs.get("variation_xrefs") or []:
            if x.get("db_source") == "dbSNP" and str(x.get("db_id")) == rs_number:
                return True
    return False


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
        clin_sig = _classification(item)
        entries.append({
            "id": uid,
            "title": item.get("title", ""),
            "gene": item.get("gene_sort", gene),
            "clinical_significance": clin_sig.get("description", ""),
            "review_status": clin_sig.get("review_status", item.get("review_status", "")),
            "last_evaluated": clin_sig.get("last_evaluated", item.get("last_evaluated", "")),
            "variation_type": item.get("variation_type", ""),
            "url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{uid}/",
        })
    return entries


async def get_pathogenicity(rs_id: str) -> dict:
    """Get ClinVar pathogenicity for an rs ID.

    Uses the dbSNP -> ClinVar link (a plain esearch on the rs number is fuzzy and returns
    unrelated records), then prefers the single-nucleotide record carrying that dbSNP ID.
    """
    rs_number = rs_id.lower().removeprefix("rs")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{BASE}/elink.fcgi",
            params={"dbfrom": "snp", "db": "clinvar", "id": rs_number, "retmode": "json"},
        )
        r.raise_for_status()
        ids = [
            link
            for linkset in r.json().get("linksets", [])
            for db in linkset.get("linksetdbs", [])
            for link in db.get("links", [])
        ]
        if not ids:
            return {"clinical_significance": "not found", "rs_id": rs_id}

        r2 = await client.get(
            f"{BASE}/esummary.fcgi",
            params={"db": "clinvar", "id": ",".join(ids), "retmode": "json"},
        )
        r2.raise_for_status()
        result = r2.json().get("result", {})

    items = [result[i] for i in ids if i in result]
    exact = [it for it in items if _has_dbsnp_id(it, rs_number)]
    snvs = [it for it in exact if it.get("obj_type") == "single nucleotide variant"]
    pool = snvs or exact or items
    if not pool:
        return {"clinical_significance": "not found", "rs_id": rs_id}

    item = pool[0]
    clin_sig = _classification(item)
    return {
        "rs_id": rs_id,
        "clinical_significance": clin_sig.get("description") or "unknown",
        "review_status": clin_sig.get("review_status", ""),
        "title": item.get("title", ""),
        "url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{item.get('uid', '')}/",
    }
