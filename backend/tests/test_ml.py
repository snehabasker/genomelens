import json
from pathlib import Path

import pytest

from ml.features import FEATURE_NAMES, featurize, parse_change

pytest.importorskip("xgboost")
from ml.predict import predict_missense  # noqa: E402

ART = Path(__file__).resolve().parents[1] / "ml" / "artifacts"


def test_parse_change_accepts_hgvs_and_one_letter():
    assert parse_change("p.Arg52His") == ("R", 52, "H")
    assert parse_change("R52H") == ("R", 52, "H")


@pytest.mark.parametrize("bad", ["p.Arg52Arg", "p.Arg52Ter", "c.123A>G", "rs334", "", "p.Xyz1Ala"])
def test_parse_change_rejects_non_missense(bad):
    with pytest.raises(ValueError):
        parse_change(bad)


def test_feature_vector_shape_and_blosum():
    f = featurize("A", 10, "R")
    assert len(f) == len(FEATURE_NAMES)
    assert f[FEATURE_NAMES.index("blosum")] == -1


def test_prediction_is_probability_and_orders_extremes():
    conservative = predict_missense("p.Ile100Val")["score"]
    radical = predict_missense("p.Gly100Asp")["score"]
    assert 0 <= conservative <= 1 and 0 <= radical <= 1
    assert radical > conservative


def test_trained_models_beat_blosum_baseline_on_gene_held_out_split():
    m = json.loads((ART / "metrics.json").read_text())
    base = m["blosum62_baseline"]["auroc"]
    assert m["substitution_only"]["xgboost"]["auroc"] > base
    assert m["substitution_only"]["keras_mlp"]["auroc"] > base
    # protein context must add real signal over substitution-only, for every model family
    assert m["protein_context"]["xgboost"]["auroc"] > m["substitution_only"]["xgboost"]["auroc"] + 0.05
    assert m["protein_context"]["keras_cnn"]["auroc"] > m["substitution_only"]["keras_mlp"]["auroc"] + 0.05


SEQ = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVV"


def test_context_prediction_uses_sequence_and_checks_reference_residue():
    r = predict_missense("p.Gly43Asp", sequence=SEQ)
    assert r["tier"] == "protein-context" and 0 <= r["score"] <= 1 and r["keras"] is not None
    assert predict_missense("p.Gly43Asp")["tier"] == "substitution-only"
    with pytest.raises(ValueError):
        predict_missense("p.Trp43Asp", sequence=SEQ)       # residue 43 is not Trp


def test_context_features_are_finite_and_window_is_centred():
    import numpy as np
    from ml.features import CTX_NAMES, WIN, featurize_ctx
    vec, win = featurize_ctx("G", 43, "D", SEQ)
    assert len(vec) == len(FEATURE_NAMES) + len(CTX_NAMES) and np.isfinite(vec).all()
    assert win.shape == (2 * WIN + 1, 20) and win[WIN].argmax() == "ARNDCQEGHILKMFPSTWYV".index("G")
    featurize_ctx("M", 1, "L", SEQ)                          # protein terminus must not crash
