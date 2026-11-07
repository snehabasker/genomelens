"""Train and compare XGBoost and a Keras MLP on humsavar. Evaluation is split BY GENE, so a model cannot score well
by memorising a gene's pathogenic rate.  Run:  python -m ml.train   (from backend/)"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit

from . import data
from .features import FEATURE_NAMES, featurize_many

ART = Path(__file__).parent / "artifacts"
SEED = 7


def build_keras(n_features: int):
    import tensorflow as tf
    tf.keras.utils.set_random_seed(SEED)
    norm = tf.keras.layers.Normalization()
    return tf.keras.Sequential([
        tf.keras.Input(shape=(n_features,)), norm,
        tf.keras.layers.Dense(64, activation="relu"), tf.keras.layers.Dropout(0.3),
        tf.keras.layers.Dense(32, activation="relu"), tf.keras.layers.Dropout(0.2),
        tf.keras.layers.Dense(1, activation="sigmoid")]), norm


def scores(y, p) -> dict:
    return {"auroc": round(float(roc_auc_score(y, p)), 4), "auprc": round(float(average_precision_score(y, p)), 4)}


def main() -> dict:
    import tensorflow as tf
    import xgboost as xgb
    rows = data.load()
    X = featurize_many([(r["ref"], r["pos"], r["alt"]) for r in rows])
    y = np.array([r["label"] for r in rows])
    genes = np.array([r["gene"] for r in rows])
    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(X, y, genes))
    a, b = next(GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=SEED).split(X[tr], y[tr], genes[tr]))
    tr2, va = tr[a], tr[b]

    booster = xgb.XGBClassifier(n_estimators=600, max_depth=5, learning_rate=0.03, subsample=0.8, colsample_bytree=0.8,
                                eval_metric="auc", early_stopping_rounds=40, random_state=SEED, n_jobs=-1)
    booster.fit(X[tr2], y[tr2], eval_set=[(X[va], y[va])], verbose=False)

    net, norm = build_keras(X.shape[1])
    norm.adapt(X[tr2])
    net.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="binary_crossentropy")
    net.fit(X[tr2], y[tr2], validation_data=(X[va], y[va]), epochs=60, batch_size=256, verbose=0,
            callbacks=[tf.keras.callbacks.EarlyStopping(patience=6, restore_best_weights=True)])

    p_xgb, p_nn = booster.predict_proba(X[te])[:, 1], net.predict(X[te], verbose=0).ravel()
    dissimilar = -X[te][:, FEATURE_NAMES.index("blosum")]     # baseline: less similar substitution = more pathogenic
    metrics = {"dataset": "UniProt humsavar LP/P vs LB/B", "n_total": int(len(y)), "n_train": int(len(tr2)),
               "n_test": int(len(te)), "test_genes": int(len(set(genes[te]))), "positive_rate": round(float(y.mean()), 3),
               "split": "grouped by gene (no gene appears in both train and test)",
               "blosum62_baseline": scores(y[te], dissimilar), "xgboost": scores(y[te], p_xgb),
               "keras_mlp": scores(y[te], p_nn), "ensemble_mean": scores(y[te], (p_xgb + p_nn) / 2),
               "xgboost_importance": {n: round(float(v), 4) for n, v in sorted(
                   zip(FEATURE_NAMES, booster.feature_importances_), key=lambda t: -t[1])[:8]}}
    ART.mkdir(exist_ok=True)
    booster.save_model(ART / "xgb.json")
    net.save(ART / "mlp.keras")
    (ART / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    main()
