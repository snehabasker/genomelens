import httpx

BASE = "https://rest.ensembl.org"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


async def get_gene_info(gene_symbol: str) -> dict:
    """Lookup gene by symbol in human genome."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE}/lookup/symbol/homo_sapiens/{gene_symbol}",
            headers=HEADERS,
        )
        if r.status_code == 404:
            return {}
        r.raise_for_status()
        data = r.json()
    return {
        "ensembl_id": data.get("id", ""),
        "gene": data.get("display_name", gene_symbol),
        "description": data.get("description", ""),
        "chromosome": data.get("seq_region_name", ""),
        "start": data.get("start"),
        "end": data.get("end"),
        "strand": data.get("strand"),
        "biotype": data.get("biotype", ""),
    }


async def get_sequence(region: str, species: str = "human") -> str:
    """Fetch DNA sequence for a region like '17:43094000-43094100'."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{BASE}/sequence/region/{species}/{region}",
            headers={**HEADERS, "Accept": "text/plain"},
        )
        if r.status_code != 200:
            return ""
        return r.text.strip().upper()


async def vep_hgvs(hgvs_notation: str) -> list:
    """Run VEP on an HGVS notation. Returns list of consequence dicts."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{BASE}/vep/human/hgvs",
            headers=HEADERS,
            json={"hgvs_notations": [hgvs_notation]},
        )
        if r.status_code != 200:
            return []
        data = r.json()
    if not data or not isinstance(data, list):
        return []
    results = []
    for entry in data:
        for tc in entry.get("transcript_consequences", []):
            results.append({
                "transcript": tc.get("transcript_id", ""),
                "gene": tc.get("gene_symbol", ""),
                "consequence": tc.get("consequence_terms", []),
                "impact": tc.get("impact", ""),
                "amino_acids": tc.get("amino_acids", ""),
                "codons": tc.get("codons", ""),
                "sift": tc.get("sift_prediction", ""),
                "polyphen": tc.get("polyphen_prediction", ""),
                "hgvsp": tc.get("hgvsp", ""),
                "hgvsc": tc.get("hgvsc", ""),
            })
    return results


async def vep_region(chromosome: str, position: int, ref: str, alt: str) -> list:
    """Run VEP on a genomic position."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{BASE}/vep/human/region/{chromosome}:{position}-{position}/{alt}",
            headers=HEADERS,
        )
        if r.status_code != 200:
            return []
        data = r.json()
    results = []
    for entry in (data if isinstance(data, list) else []):
        for tc in entry.get("transcript_consequences", []):
            results.append({
                "transcript": tc.get("transcript_id", ""),
                "gene": tc.get("gene_symbol", ""),
                "consequence": tc.get("consequence_terms", []),
                "impact": tc.get("impact", ""),
                "amino_acids": tc.get("amino_acids", ""),
                "sift": tc.get("sift_prediction", ""),
                "polyphen": tc.get("polyphen_prediction", ""),
                "hgvsp": tc.get("hgvsp", ""),
            })
    return results
