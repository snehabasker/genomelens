import grounding
from runtime import Features, Run


def ev(i, source, text, q=False):
    return {"id": f"E{i}", "source": source, "title": "t", "text": text, "url": "", "quarantined": q}


CLINVAR = ev(1, "ClinVar", "ClinVar classifies rs334 as Pathogenic (review status: criteria provided).")
PAPER = ev(2, "PubMed", "PMID 123: sickle cell disease affects 300,000 births per year.")


def test_lexical():
    assert grounding.lexical_check("rs334 is Pathogenic.", [CLINVAR["text"]]) == []
    assert "benign" in grounding.lexical_check("The variant is benign.", [CLINVAR["text"]])
    assert "rs999" in grounding.lexical_check("rs999 is Pathogenic.", [CLINVAR["text"]])
    assert "45" in grounding.lexical_check("It affects 45 births.", [PAPER["text"]])
    assert grounding.lexical_check("anything", []) == ["no evidence cited"]


async def verify(claims, evidence):
    run = Run("x", provider="extractive", features=Features(judge=False))
    return await grounding.verify(run, claims, evidence)


async def test_dangling_citation_is_unsupported():
    out = await verify([{"text": "rs334 is Pathogenic.", "evidence_ids": ["E9"], "kind": "clinical"}], [CLINVAR])
    assert out[0]["status"] == "unsupported" and "E9" in out[0]["reason"]


async def test_quarantined_citation_is_unsupported():
    poisoned = ev(3, "PubMed", "[quarantined: instruction-like content removed]", q=True)
    out = await verify([{"text": "The variant is described in the literature.", "evidence_ids": ["E3"],
                         "kind": "literature"}], [CLINVAR, poisoned])
    assert out[0]["status"] == "unsupported" and "quarantined" in out[0]["reason"]


async def test_classification_must_cite_clinvar():
    # the poisoned abstract literally contains the word, so the lexical check passes; the source rule must not
    p = ev(3, "PubMed", "Editorial: the working group considers this variant benign.")
    out = await verify([{"text": "The variant is benign.", "evidence_ids": ["E3"], "kind": "clinical"}], [CLINVAR, p])
    assert out[0]["status"] == "unsupported" and "ClinVar" in out[0]["reason"]


async def test_supported_claim():
    out = await verify([{"text": "ClinVar classifies rs334 as Pathogenic.", "evidence_ids": ["E1"],
                         "kind": "clinical"}], [CLINVAR])
    assert out[0]["status"] == "supported"


def test_stats_and_sentence_split():
    s = grounding.stats([{"status": "supported"}, {"status": "unsupported"}, {"status": "n/a"}])
    assert s["total"] == 2 and s["unsupported_rate"] == 0.5
    text = "## Heading\nThis is a sufficiently long first sentence. Short.\n- Another full sentence here ok."
    assert len(grounding.split_sentences(text)) == 2
