import time

from tools import net as httpx

PRIMARY = "https://rest.ensembl.org"                # GRCh38
MIRROR = "https://grch37.rest.ensembl.org"          # GRCh37 - healthy when the primary is not
_primary_down_until = 0.0   # circuit breaker: after a primary failure, go straight to the mirror for 60s
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


async def _request(method: str, path: str, *, failover: bool, extensions: dict = None, **kw):
    """Try the GRCh38 endpoint, then (if `failover`) the GRCh37 mirror.

    Failover is only used for answers that don't depend on the genome build - which gene a
    symbol is, what a variant does to the protein. Coordinates and sequence never fail over.
    Returns (response, build).
    """
    global _primary_down_until
    last_exc, last_resp = None, None
    for base, build in ((PRIMARY, "GRCh38"), (MIRROR, "GRCh37")):
        if build == "GRCh37" and not failover:
            break
        if build == "GRCh38" and failover and time.monotonic() < _primary_down_until:
            continue
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                # one shot on the primary when a mirror exists: the mirror is the retry
                ext = dict(extensions or {})
                if failover and build == "GRCh38":
                    ext["no_retry"] = True
                r = await client.request(method, base + path, extensions=ext, **kw)
            if r.status_code < 500:
                return r, build
            last_resp = r
        except httpx.HTTPError as e:
            last_exc = e
        if build == "GRCh38":
            _primary_down_until = time.monotonic() + 60
    if last_resp is None and last_exc is not None:
        raise last_exc
    return last_resp, "GRCh38"


async def get_gene_info(gene_symbol: str) -> dict:
    """Lookup gene by symbol in human genome. {} if the symbol is unknown."""
    r, build = await _request("GET", f"/lookup/symbol/homo_sapiens/{gene_symbol}", failover=True,
                              headers=HEADERS)
    if r.status_code in (400, 404):
        return {}
    r.raise_for_status()
    data = r.json()
    return {
        "ensembl_id": data.get("id", ""),
        "gene": data.get("display_name", gene_symbol),
        "description": data.get("description", ""),
        "chromosome": data.get("seq_region_name", ""),
        "start": data.get("start") if build == "GRCh38" else None,
        "end": data.get("end") if build == "GRCh38" else None,
        "strand": data.get("strand"),
        "biotype": data.get("biotype", ""),
        "build": build,
    }


async def get_sequence(region: str, species: str = "human") -> str:
    """Fetch DNA sequence for a region like '17:43094000-43094100' (GRCh38 only)."""
    if time.monotonic() < _primary_down_until:
        return ""
    r, _ = await _request("GET", f"/sequence/region/{species}/{region}", failover=False,
                          headers={"Accept": "text/plain"}, extensions={"optional": True, "no_retry": True})
    if r.status_code != 200:
        return ""
    seq = r.text.strip().upper()
    # Guard against error bodies being mistaken for DNA
    return seq if seq and set(seq) <= set("ACGTN") else ""


def _consequences(data, with_codons: bool) -> list:
    results = []
    for entry in (data if isinstance(data, list) else []):
        for tc in entry.get("transcript_consequences", []):
            row = {
                "transcript": tc.get("transcript_id", ""),
                "gene": tc.get("gene_symbol", ""),
                "consequence": tc.get("consequence_terms", []),
                "impact": tc.get("impact", ""),
                "amino_acids": tc.get("amino_acids", ""),
                "sift": tc.get("sift_prediction", ""),
                "polyphen": tc.get("polyphen_prediction", ""),
                "hgvsp": tc.get("hgvsp", ""),
            }
            if with_codons:
                row.update(codons=tc.get("codons", ""), hgvsc=tc.get("hgvsc", ""))
            results.append(row)
    return results


async def vep_hgvs(hgvs_notation: str) -> list:
    """Run VEP on an HGVS notation. Returns list of consequence dicts."""
    r, _ = await _request("POST", "/vep/human/hgvs", failover=True, headers=HEADERS,
                          json={"hgvs_notations": [hgvs_notation]})
    if r.status_code != 200:
        return []
    return _consequences(r.json(), with_codons=True)


async def vep_region(chromosome: str, position: int, ref: str, alt: str) -> list:
    """Run VEP on a genomic position (GRCh38 coordinates, so no failover)."""
    r, _ = await _request("GET", f"/vep/human/region/{chromosome}:{position}-{position}/{alt}",
                          failover=False, headers=HEADERS)
    if r.status_code != 200:
        return []
    return _consequences(r.json(), with_codons=False)
