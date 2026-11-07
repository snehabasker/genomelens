"""Inference: a pathogenicity *prior* for a missense change. Substitution-only features, so it is a weak signal
(see artifacts/metrics.json) and must never replace ClinVar or the grounded agents. XGBoost is required;
the Keras model is used only if TensorFlow is installed."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np

from .features import featurize_many, parse_change

ART = Path(__file__).parent / "artifacts"


@lru_cache(maxsize=1)
def _xgb():
    import xgboost as xgb
    m = xgb.XGBClassifier()
    m.load_model(ART / "xgb.json")
    return m


@lru_cache(maxsize=1)
def _keras():
    try:
        import tensorflow as tf
        return tf.keras.models.load_model(ART / "mlp.keras")
    except Exception:
        return None


def predict_missense(change: str) -> dict:
    """'p.Arg52His' | 'R52H' -> {'change', 'xgboost', 'keras'|None, 'score', 'note'} (probabilities of LP/P)."""
    ref, pos, alt = parse_change(change)
    x = featurize_many([(ref, pos, alt)])
    p_x = float(_xgb().predict_proba(x)[0, 1])
    net = _keras()
    p_k = float(net.predict(x, verbose=0)[0, 0]) if net is not None else None
    score = p_x if p_k is None else float(np.mean([p_x, p_k]))
    return {"change": f"{ref}{pos}{alt}", "xgboost": round(p_x, 4), "keras": None if p_k is None else round(p_k, 4),
            "score": round(score, 4), "note": "substitution-only prior; not a clinical classification"}
