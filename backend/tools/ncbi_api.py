import httpx
import os
from typing import Optional

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
API_KEY = os.getenv("NCBI_API_KEY", "")

HEADERS = {"Accept": "application/json"}
PARAMS_BASE = {"api_key": API_KEY} if API_KEY else {}


async def search_snp(rs_id: str) -> dict:
    """Fetch SNP summary for an rs ID."""
    numeric_id = rs_id.lstrip("rs")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE}/esummary.fcgi",
            params={**PARAMS_BASE, "db": "snp", "id": numeric_id, "retmode": "json"},
        )
        r.raise_for_status()
        data = r.json()
    result = data.get("result", {})
    snp = result.get(numeric_id, {})
    if not snp:
        return {}
    # Extract useful fields
    genes = snp.get("genes", [])
    gene_name = genes[0].get("name", "") if genes else snp.get("gene", "")
    chrpos = snp.get("chrpos", "")  # e.g. "17:43094464"
    chrom, pos = (chrpos.split(":") + [""])[:2]
    return {
        "rs_id": rs_id,
        "gene": gene_name,
        "chromosome": chrom,
        "position": int(pos) if pos.isdigit() else None,
        "alleles": snp.get("alleles", ""),
        "class": snp.get("snp_class", "snp"),
        "clinical_significance": snp.get("clinical_significance", ""),
        "fxn_class": snp.get("fxn_class", ""),
    }


async def search_gene(gene_name: str) -> dict:
    """Search NCBI Gene for gene info."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE}/esearch.fcgi",
            params={**PARAMS_BASE, "db": "gene", "term": f"{gene_name}[Gene Name] AND human[Organism]",
                    "retmode": "json", "retmax": "1"},
        )
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return {}

        r2 = await client.get(
            f"{BASE}/esummary.fcgi",
            params={**PARAMS_BASE, "db": "gene", "id": ids[0], "retmode": "json"},
        )
        r2.raise_for_status()
        result = r2.json().get("result", {})
    gene = result.get(ids[0], {})
    chrloc = gene.get("maplocation", "")
    return {
        "gene_id": ids[0],
        "gene": gene.get("name", gene_name),
        "full_name": gene.get("description", ""),
        "chromosome": gene.get("chromosome", ""),
        "map_location": chrloc,
        "summary": gene.get("summary", ""),
    }


async def fetch_sequence(accession: str, start: int, end: int) -> str:
    """Fetch a subsequence from NCBI nuccore."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{BASE}/efetch.fcgi",
            params={**PARAMS_BASE, "db": "nuccore", "id": accession,
                    "rettype": "fasta", "retmode": "text",
                    "seq_start": start, "seq_stop": end},
        )
        r.raise_for_status()
        text = r.text
    # Strip FASTA header
    lines = [l for l in text.strip().split("\n") if not l.startswith(">")]
    return "".join(lines).upper()
