import httpx

BASE = "https://api.pharmgkb.org/v1/data"


async def get_variant_drugs(rs_id: str) -> list:
    """Fetch drug-variant annotations from PharmGKB."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{BASE}/clinicalAnnotation",
            params={"location.name": rs_id, "view": "base"},
            headers={"Accept": "application/json"},
        )
        if r.status_code != 200:
            return []
        data = r.json()

    annotations = data.get("data", [])
    results = []
    for ann in annotations[:10]:
        drugs = [d.get("name", "") for d in ann.get("relatedChemicals", [])]
        results.append({
            "drugs": drugs,
            "phenotype": ann.get("phenotypes", [{}])[0].get("name", "") if ann.get("phenotypes") else "",
            "significance": ann.get("clinicalAnnotationTypes", [""])[0] if ann.get("clinicalAnnotationTypes") else "",
            "level": ann.get("level", ""),
            "url": f"https://www.pharmgkb.org/clinicalAnnotation/{ann.get('id', '')}",
        })
    return results


async def get_gene_drugs(gene: str) -> list:
    """Fetch drug-gene annotations from PharmGKB."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{BASE}/clinicalAnnotation",
            params={"gene.symbol": gene, "view": "base"},
            headers={"Accept": "application/json"},
        )
        if r.status_code != 200:
            return []
        data = r.json()

    annotations = data.get("data", [])
    results = []
    seen_drugs = set()
    for ann in annotations[:20]:
        for drug in ann.get("relatedChemicals", []):
            dname = drug.get("name", "")
            if dname and dname not in seen_drugs:
                seen_drugs.add(dname)
                results.append({
                    "drug": dname,
                    "level": ann.get("level", ""),
                    "phenotype": ann.get("phenotypes", [{}])[0].get("name", "") if ann.get("phenotypes") else "",
                })
    return results


async def get_dgidb_interactions(gene: str) -> list:
    """Fetch drug-gene interactions from DGIdb."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://dgidb.org/api/v2/interactions.json",
            params={"genes": gene},
        )
        if r.status_code != 200:
            return []
        data = r.json()

    interactions = []
    matched = data.get("matchedTerms", [])
    for term in matched:
        for inter in term.get("interactions", [])[:10]:
            interactions.append({
                "drug": inter.get("drugName", ""),
                "interaction_type": inter.get("interactionTypes", [""]),
                "sources": inter.get("sources", []),
            })
    return interactions
