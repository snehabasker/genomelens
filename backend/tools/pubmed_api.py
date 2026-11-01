import xml.etree.ElementTree as ET

from tools import net as httpx

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


async def search_papers(query: str, max_results: int = 5) -> list:
    """Search PubMed and return article summaries."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{BASE}/esearch.fcgi",
            params={"db": "pubmed", "term": query, "retmode": "json", "retmax": str(max_results)},
        )
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []

        r2 = await client.get(
            f"{BASE}/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
        )
        r2.raise_for_status()
        result = r2.json().get("result", {})

    papers = []
    for uid in ids:
        item = result.get(uid, {})
        if not item:
            continue
        authors = item.get("authors", [])
        author_str = ", ".join(a.get("name", "") for a in authors[:3])
        if len(authors) > 3:
            author_str += " et al."
        papers.append({
            "pmid": uid,
            "title": item.get("title", ""),
            "authors": author_str,
            "journal": item.get("source", ""),
            "year": item.get("pubdate", "")[:4],
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
        })
    return papers


async def fetch_abstract(pmid: str) -> str:
    """Title + abstract text for a PubMed article (parsed from XML: the plain-text 'abstract' format
    leads with a citation header and author affiliations, which is not the abstract)."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE}/efetch.fcgi",
            params={"db": "pubmed", "id": pmid, "retmode": "xml"},
        )
        if r.status_code != 200:
            return ""
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        return ""
    title = "".join(root.findtext(".//ArticleTitle") or "").strip()
    parts = []
    for node in root.iter("AbstractText"):
        text = "".join(node.itertext()).strip()
        if text:
            label = node.get("Label")
            parts.append(f"{label}: {text}" if label else text)
    return " ".join(x for x in [title + "." if title else "", " ".join(parts)] if x).strip()
