import httpx

# PharmGKB was rebranded ClinPGx; the old api.pharmgkb.org host no longer resolves.
BASE = "https://api.clinpgx.org/v1/data"
DGIDB_GRAPHQL = "https://dgidb.org/api/graphql"


def _annotation_fields(ann: dict) -> dict:
    allele_phenotypes = ann.get("allelePhenotypes") or []
    level = ann.get("levelOfEvidence") or {}
    types = ann.get("types") or []
    return {
        "drugs": [d.get("name", "") for d in ann.get("relatedChemicals") or []],
        "phenotype": allele_phenotypes[0].get("phenotype", "") if allele_phenotypes else "",
        "significance": types[0] if types else "",
        "level": level.get("term", "") if isinstance(level, dict) else "",
        "url": f"https://www.clinpgx.org/clinicalAnnotation/{ann.get('accessionId', '')}",
    }


async def _clinical_annotations(params: dict) -> list:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                f"{BASE}/clinicalAnnotation",
                params={**params, "view": "base"},
                headers={"Accept": "application/json"},
            )
            if r.status_code != 200:
                return []
            return r.json().get("data", [])
    except httpx.HTTPError:
        return []


async def get_variant_drugs(rs_id: str) -> list:
    """Fetch drug-variant annotations from ClinPGx (formerly PharmGKB)."""
    annotations = await _clinical_annotations({"location.fingerprint": rs_id})
    return [_annotation_fields(ann) for ann in annotations[:10]]


async def get_gene_drugs(gene: str) -> list:
    """Fetch drug-gene annotations from ClinPGx (formerly PharmGKB)."""
    annotations = await _clinical_annotations({"location.genes.symbol": gene})
    results = []
    seen_drugs = set()
    for ann in annotations[:20]:
        fields = _annotation_fields(ann)
        for dname in fields["drugs"]:
            if dname and dname not in seen_drugs:
                seen_drugs.add(dname)
                results.append({
                    "drug": dname,
                    "level": fields["level"],
                    "phenotype": fields["phenotype"],
                })
    return results


_DGIDB_QUERY = """
query($names: [String!]!) {
  genes(names: $names) {
    nodes {
      name
      interactions {
        drug { name }
        interactionScore
        interactionTypes { type }
        sources { sourceDbName }
      }
    }
  }
}
"""


async def get_dgidb_interactions(gene: str) -> list:
    """Fetch drug-gene interactions from DGIdb (GraphQL API; the v2 REST API is retired)."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                DGIDB_GRAPHQL,
                json={"query": _DGIDB_QUERY, "variables": {"names": [gene]}},
            )
            if r.status_code != 200:
                return []
            data = r.json()
    except httpx.HTTPError:
        return []

    interactions = []
    nodes = ((data.get("data") or {}).get("genes") or {}).get("nodes") or []
    for node in nodes:
        ranked = sorted(node.get("interactions") or [],
                        key=lambda i: i.get("interactionScore") or 0, reverse=True)
        for inter in ranked[:10]:
            interactions.append({
                "drug": (inter.get("drug") or {}).get("name", ""),
                "interaction_type": [t.get("type", "") for t in inter.get("interactionTypes") or [] if t.get("type")],
                "sources": [s.get("sourceDbName", "") for s in inter.get("sources") or []],
            })
    return interactions
