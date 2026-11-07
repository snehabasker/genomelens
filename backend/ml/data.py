"""UniProt humsavar: expert-curated missense variants labelled LP/P (1) or LB/B (0). VUS (US) are dropped."""
from __future__ import annotations

import urllib.request
from pathlib import Path

from .features import AA, THREE

URL = "https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/variants/humsavar.txt"
CACHE = Path(__file__).parent / "data" / "humsavar.txt"


def download(path: Path = CACHE) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(URL, timeout=120) as r:
            path.write_bytes(r.read())
    return path


def load(path: Path | None = None) -> list[dict]:
    """-> [{gene, ref, pos, alt, label}] for every unambiguous LP/P or LB/B missense."""
    rows, seen = [], set()
    for line in (path or download()).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5 or not parts[3].startswith("p.") or parts[4] not in ("LP/P", "LB/B"):
            continue
        gene, change = parts[0], parts[3][2:]
        try:
            ref, pos, alt = THREE[change[:3]], int(change[3:-3]), THREE[change[-3:]]
        except (KeyError, ValueError):
            continue
        if ref not in AA or alt not in AA or (gene, ref, pos, alt) in seen:
            continue
        seen.add((gene, ref, pos, alt))
        rows.append({"gene": gene, "acc": parts[1], "ref": ref, "pos": pos, "alt": alt, "label": int(parts[4] == "LP/P")})
    return rows


FASTA = Path(__file__).parent / "data" / "human.fasta"


def load_sequences(path: Path = FASTA) -> dict[str, str]:
    """accession -> sequence from a UniProt FASTA (reviewed human proteins)."""
    seqs, acc, buf = {}, None, []
    for line in path.read_text().splitlines():
        if line.startswith(">"):
            if acc:
                seqs[acc] = "".join(buf)
            acc, buf = line.split("|")[1], []
        else:
            buf.append(line.strip())
    if acc:
        seqs[acc] = "".join(buf)
    return seqs
