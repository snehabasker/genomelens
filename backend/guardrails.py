"""Input guardrails and untrusted-text scanning.

Two different threats, two different entry points:

  check_input(query)      direct attacks and garbage typed into the box
  scan_untrusted(text)    indirect prompt injection hiding in retrieved evidence (PubMed etc.)

Design rule: the only thing allowed past the front door is a *recognised variant grammar*
(rsID, GENE, GENE + c.HGVS, raw DNA). Everything else gets an explicit, explained refusal
with suggestions, never a best-effort guess handed to an LLM.
"""
from __future__ import annotations

import re
import unicodedata

MAX_QUERY_LEN = 1200
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿‪‫‬‭‮"), None)

INJECTION_PATTERNS = [
    r"ignore (all |any |the |your )?(previous|prior|above|earlier|preceding)",
    r"disregard .{0,40}(instruction|rule|prompt|guideline)",
    r"forget (everything|all|your) .{0,30}(instruction|rule|prompt|above)",
    r"\byou are (now|no longer)\b",
    r"\b(system|developer) (prompt|message|instruction)s?\b",
    r"\b(reveal|show|print|repeat|leak|output) .{0,30}(prompt|instruction|api[ _-]?key|secret|password)",
    r"\bjailbreak\b|\bdan mode\b|developer mode",
    r"\bpretend (to be|you are)\b|\broleplay as\b|\bact as (a|an|if)\b",
    r"</?\s*(system|assistant|user|instructions?|prompt)\s*>",
    r"<\|[^>]{1,30}\|>|\[/?inst\]|###\s*(system|instruction)",
    r"\boverride .{0,20}(safety|rule|guardrail|polic)",
    r"\b(new|updated) instructions?\s*:",
    r"\bdo not (follow|obey|use) .{0,30}(instruction|rule|prompt)",
    r"(respond|reply|answer|say|state|conclude|report) (only )?(with|that)? ?.{0,40}\b(is|as) (completely |totally )?(benign|harmless|safe)\b.{0,20}(regardless|ignor)",
]
_INJECTION_RE = re.compile("|".join(f"(?:{p})" for p in INJECTION_PATTERNS), re.I | re.S)

_MARKUP_RE = re.compile(
    r"<\s*/?\s*(script|iframe|img|svg|style|html|body|a|form|object|embed)\b|javascript:|on\w+\s*=|"
    r"\bunion\s+select\b|\bdrop\s+table\b|;\s*--|'\s*or\s*'?1'?\s*=\s*'?1|\$\(|`|&&|\|\||\.\./|\{\{|\}\}|\$\{",
    re.I)

_ADVICE_RE = re.compile(
    r"\bshould i (stop|start|take|change|quit|skip|increase|decrease|have|get)\b|"
    r"\bwhat (dose|dosage)\b|\bhow (much|many) .{0,25}\bshould i\b|\bam i (going|likely) to (die|get)\b|"
    r"\bdo i have (cancer|the disease)\b|\bdiagnos(e|is)\b.{0,15}\bme\b|\bprescribe\b|\bstop taking\b|"
    r"\bwill i (die|get|develop)\b", re.I)

# Common names people actually type -> an identifier the pipeline can resolve.
ALIASES = {
    "cyp2c19*2": "rs4244285", "cyp2c19*3": "rs4986893", "cyp2c9*2": "rs1799853",
    "cyp2c9*3": "rs1057910", "cyp2d6*4": "rs3892097", "tpmt*3c": "rs1142345",
    "dpyd*2a": "rs3918290", "slco1b1*5": "rs4149056",
    "mthfr c677t": "rs1801133", "mthfr c.677c>t": "rs1801133", "c677t": "rs1801133",
    "mthfr a1298c": "rs1801131", "mthfr c.1298a>c": "rs1801131",
    "factor v leiden": "rs6025", "f5 leiden": "rs6025", "sickle cell": "rs334",
    "cftr f508del": "rs113993960", "f508del": "rs113993960",
}

_RSID = re.compile(r"^rs[1-9]\d{0,11}$", re.I)
_GENE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{1,14}$")
_GENE_HGVS = re.compile(r"^([A-Za-z][A-Za-z0-9-]{1,14})\s+(c\.[A-Za-z0-9_>+\-*?=()]{2,40})$", re.I)
_DNA = re.compile(r"^[ACGTNacgtn\s]{10,}$")

SUGGESTIONS = ["rs1801133", "BRCA1 c.5266dup", "rs334", "TP53 c.817C>T"]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").translate(_ZERO_WIDTH)
    text = "".join(ch for ch in text if ch in "\n\t " or unicodedata.category(ch)[0] != "C")
    return re.sub(r"[ \t]+", " ", text).strip()


def _refuse(kind: str, message: str, matched: str = "", normalized: str = "") -> dict:
    return {"ok": False, "kind": kind, "message": message, "matched": matched or None,
            "suggestions": SUGGESTIONS, "normalized": normalized, "rewritten": False}


def check_input(query: str) -> dict:
    """Return {ok, kind, message, normalized, suggestions, matched, rewritten}."""
    if not isinstance(query, str):
        return _refuse("malformed", "The query must be text.")
    q = normalize(query)
    if not q:
        return _refuse("empty", "Enter a variant (rsID or GENE c.HGVS), a gene symbol, or a DNA sequence.")
    if len(q) > MAX_QUERY_LEN:
        return _refuse("too_long", f"Input is {len(q):,} characters; the limit is {MAX_QUERY_LEN:,}. "
                                   "Genome Lens analyses one variant at a time.", normalized=q[:80])

    m = _INJECTION_RE.search(q)
    if m:
        return _refuse("prompt_injection",
                       "This looks like an attempt to give the AI new instructions. "
                       "Genome Lens only accepts variant identifiers, so nothing was sent to a model.",
                       matched=m.group(0)[:80], normalized=q[:120])
    m = _MARKUP_RE.search(q)
    if m:
        return _refuse("unsafe_markup", "The input contains markup, script or query syntax, "
                       "which is never a valid variant. It was rejected before any lookup.",
                       matched=m.group(0)[:80], normalized=q[:120])
    m = _ADVICE_RE.search(q)
    if m:
        return _refuse("medical_advice",
                       "Genome Lens interprets variants; it cannot give personal medical advice or tell "
                       "you to change a medication. Ask about the variant itself and discuss results "
                       "with a clinician or genetic counsellor.", matched=m.group(0)[:80], normalized=q[:120])

    alias = ALIASES.get(q.lower())
    if alias:
        return {"ok": True, "kind": "alias", "message": f"Interpreted “{q}” as {alias}.",
                "normalized": alias, "suggestions": [], "matched": q, "rewritten": True}

    if _RSID.match(q):
        return {"ok": True, "kind": "rsid", "normalized": q.lower(), "message": "", "suggestions": [],
                "matched": None, "rewritten": q != q.lower()}
    if re.match(r"^rs\d*$", q, re.I):
        return _refuse("invalid_rsid", "dbSNP IDs look like rs1801133: “rs” followed by 1-12 digits, "
                       "not starting with 0.", matched=q[:40], normalized=q[:40])
    m = _GENE_HGVS.match(q)
    if m:
        norm = f"{m.group(1).upper()} {m.group(2)}"
        return {"ok": True, "kind": "gene_hgvs", "normalized": norm, "message": "", "suggestions": [],
                "matched": None, "rewritten": norm != q}
    if _DNA.match(q):
        seq = re.sub(r"\s+", "", q).upper()
        if len(seq) > 1000:
            return _refuse("too_long", "Sequences are limited to 1,000 bases.", normalized=seq[:40])
        return {"ok": True, "kind": "raw_dna", "normalized": seq, "message": "", "suggestions": [],
                "matched": None, "rewritten": seq != q}
    if _GENE.match(q):
        return {"ok": True, "kind": "gene", "normalized": q.upper(), "message": "", "suggestions": [],
                "matched": None, "rewritten": q != q.upper()}

    hint = ""
    if re.search(r"\*\d", q):
        hint = " Star-allele names are only supported for common pharmacogenes; try its rsID instead."
    if re.match(r"^c\.", q, re.I):
        hint = " A bare c. change needs a gene, e.g. “BRCA1 c.5266dup”."
    return _refuse("unrecognized", "That isn't a variant format Genome Lens understands "
                   "(rsID, GENE c.HGVS, gene symbol, or raw DNA)." + hint, normalized=q[:120])


def scan_untrusted(text: str) -> tuple[bool, str]:
    """Is retrieved text trying to instruct the model? Returns (quarantine?, reason)."""
    if not text:
        return False, ""
    t = normalize(text)
    m = _INJECTION_RE.search(t)
    if m:
        return True, f"matched “{m.group(0)[:60]}”"
    return False, ""
