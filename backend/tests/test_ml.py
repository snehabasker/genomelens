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
    assert m["xgboost"]["auroc"] > m["blosum62_baseline"]["auroc"]
    assert m["keras_mlp"]["auroc"] > m["blosum62_baseline"]["auroc"]
