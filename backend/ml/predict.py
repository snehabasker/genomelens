"""Inference: a pathogenicity *prior* for a missense change. Never a replacement for ClinVar or the grounded agents.

Two tiers, chosen by what the caller can supply:
  * protein context (preferred): pass `sequence=` (wild-type protein) or `accession=` (UniProt, fetched + cached).
    XGBoost + TensorFlow CNN ensemble; held-out AUROC ~0.80 (artifacts/metrics.json).
  * substitution only: just the change. XGBoost + Keras MLP; held-out AUROC ~0.71.
"""
from __future__ import annotations

import os
import urllib.request
from functools import lru_cache
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np

from .features import featurize_ctx, featurize_many, parse_change

ART = Path(__file__).parent / "artifacts"


@lru_cache(maxsize=4)
def _xgb(name: str):
    import xgboost as xgb
    m = xgb.XGBClassifier()
    m.load_model(ART / name)
    return m


@lru_cache(maxsize=4)
def _keras(name: str):
    try:
        import tensorflow as tf
        return tf.keras.models.load_model(ART / name)
    except Exception:
        return None


@lru_cache(maxsize=256)
def fetch_sequence(accession: str) -> str:
    with urllib.request.urlopen(f"https://rest.uniprot.org/uniprotkb/{accession}.fasta", timeout=20) as r:
        return "".join(r.read().decode().splitlines()[1:])


def predict_missense(change: str, sequence: str | None = None, accession: str | None = None) -> dict:
    """'p.Arg52His' | 'R52H' -> {'change', 'tier', 'xgboost', 'keras', 'score', 'note'} (probabilities of LP/P).
    Raises ValueError if the reference residue does not match the supplied/fetched sequence."""
    ref, pos, alt = parse_change(change)
    if sequence is None and accession:
        sequence = fetch_sequence(accession)
    if sequence:
        vec, win = featurize_ctx(ref, pos, alt, sequence)
        x = np.asarray([vec], dtype=np.float32)
        p_x = float(_xgb("xgb_ctx.json").predict_proba(x)[0, 1])
        net = _keras("cnn_ctx.keras")
        p_k = float(net.predict({"window": win[None], "tabular": x}, verbose=0)[0, 0]) if net is not None else None
        tier = "protein-context"
    else:
        x = featurize_many([(ref, pos, alt)])
        p_x = float(_xgb("xgb.json").predict_proba(x)[0, 1])
        net = _keras("mlp.keras")
        p_k = float(net.predict(x, verbose=0)[0, 0]) if net is not None else None
        tier = "substitution-only"
    score = p_x if p_k is None else float(np.mean([p_x, p_k]))
    return {"change": f"{ref}{pos}{alt}", "tier": tier, "xgboost": round(p_x, 4),
            "keras": None if p_k is None else round(p_k, 4), "score": round(score, 4),
            "note": "learned prior, not a clinical classification"}
