"""Train and compare models on UniProt humsavar. Evaluation is split BY GENE, so a model cannot score well by
memorising a gene's pathogenic rate.  Run:  python -m ml.train   (from backend/)

Two tiers:
  substitution-only  : XGBoost + Keras MLP on amino-acid change features (works without any protein sequence)
  protein-context    : + features from the wild-type sequence around the site; XGBoost, and a TensorFlow
                       1D-CNN over the +-15 residue window fused with the tabular features
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit

from . import data
from .features import FEATURE_NAMES, CTX_NAMES, WIN, featurize_ctx

ART = Path(__file__).parent / "artifacts"
SEED = 7
N_BASE = len(FEATURE_NAMES)


def build_mlp(n_features: int, X_adapt):
    import tensorflow as tf
    tf.keras.utils.set_random_seed(SEED)
    norm = tf.keras.layers.Normalization()
    norm.adapt(X_adapt)
    return tf.keras.Sequential([
        tf.keras.Input(shape=(n_features,)), norm,
        tf.keras.layers.Dense(64, activation="relu"), tf.keras.layers.Dropout(0.3),
        tf.keras.layers.Dense(32, activation="relu"), tf.keras.layers.Dropout(0.2),
        tf.keras.layers.Dense(1, activation="sigmoid")])


def build_cnn(n_tab: int, X_adapt):
    """Window one-hot (31x20) -> Conv1D stack -> pooled, fused with the normalised tabular features."""
    import tensorflow as tf
    L = tf.keras.layers
    tf.keras.utils.set_random_seed(SEED)
    win = tf.keras.Input(shape=(2 * WIN + 1, 20), name="window")
    tab = tf.keras.Input(shape=(n_tab,), name="tabular")
    norm = L.Normalization()
    norm.adapt(X_adapt)
    x = L.Conv1D(48, 5, padding="same", activation="relu")(win)
    x = L.Conv1D(48, 3, padding="same", activation="relu")(x)
    x = L.Concatenate()([L.GlobalMaxPooling1D()(x), L.GlobalAveragePooling1D()(x), L.Flatten()(L.Cropping1D((WIN - 2, WIN - 2))(win))])
    x = L.Concatenate()([L.Dropout(0.3)(x), norm(tab)])
    x = L.Dropout(0.3)(L.Dense(96, activation="relu")(x))
    x = L.Dense(32, activation="relu")(x)
    return tf.keras.Model([win, tab], L.Dense(1, activation="sigmoid")(x))


def scores(y, p) -> dict:
    return {"auroc": round(float(roc_auc_score(y, p)), 4), "auprc": round(float(average_precision_score(y, p)), 4)}


def main() -> dict:
    import tensorflow as tf
    import xgboost as xgb
    rows, seqs = data.load(), data.load_sequences()
    rows = [r for r in rows if r["acc"] in seqs and 1 <= r["pos"] <= len(seqs[r["acc"]])
            and seqs[r["acc"]][r["pos"] - 1] == r["ref"]]
    feats = [featurize_ctx(r["ref"], r["pos"], r["alt"], seqs[r["acc"]]) for r in rows]
    X = np.asarray([f[0] for f in feats], dtype=np.float32)
    W = np.stack([f[1] for f in feats])
    y = np.array([r["label"] for r in rows])
    genes = np.array([r["gene"] for r in rows])

    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(X, y, genes))
    a, b = next(GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=SEED).split(X[tr], y[tr], genes[tr]))
    tr2, va = tr[a], tr[b]
    stop = lambda: [tf.keras.callbacks.EarlyStopping(patience=6, restore_best_weights=True)]

    def fit_xgb(cols, **kw):
        m = xgb.XGBClassifier(eval_metric="auc", early_stopping_rounds=60, random_state=SEED, n_jobs=-1, subsample=0.8,
                              colsample_bytree=0.8, **kw)
        m.fit(X[tr2][:, cols], y[tr2], eval_set=[(X[va][:, cols], y[va])], verbose=False)
        return m

    base, allc = list(range(N_BASE)), list(range(X.shape[1]))
    xgb_sub = fit_xgb(base, n_estimators=600, max_depth=5, learning_rate=0.03)
    xgb_ctx = fit_xgb(allc, n_estimators=1500, max_depth=6, learning_rate=0.02, min_child_weight=3)

    mlp = build_mlp(N_BASE, X[tr2][:, base])
    mlp.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="binary_crossentropy")
    mlp.fit(X[tr2][:, base], y[tr2], validation_data=(X[va][:, base], y[va]), epochs=60, batch_size=256, verbose=0,
            callbacks=stop())

    cnn = build_cnn(X.shape[1], X[tr2])
    cnn.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="binary_crossentropy")
    cnn.fit({"window": W[tr2], "tabular": X[tr2]}, y[tr2], validation_data=({"window": W[va], "tabular": X[va]}, y[va]),
            epochs=60, batch_size=256, verbose=0, callbacks=stop())

    p_xs = xgb_sub.predict_proba(X[te][:, base])[:, 1]
    p_ml = mlp.predict(X[te][:, base], verbose=0).ravel()
    p_xc = xgb_ctx.predict_proba(X[te])[:, 1]
    p_cn = cnn.predict({"window": W[te], "tabular": X[te]}, verbose=0).ravel()
    names = FEATURE_NAMES + CTX_NAMES
    metrics = {
        "dataset": "UniProt humsavar LP/P vs LB/B + Swiss-Prot human sequences", "n_total": int(len(y)),
        "n_train": int(len(tr2)), "n_test": int(len(te)), "test_genes": int(len(set(genes[te]))),
        "positive_rate": round(float(y.mean()), 3),
        "split": "grouped by gene (no gene appears in both train and test)",
        "blosum62_baseline": scores(y[te], -X[te][:, FEATURE_NAMES.index("blosum")]),
        "substitution_only": {"xgboost": scores(y[te], p_xs), "keras_mlp": scores(y[te], p_ml),
                              "ensemble": scores(y[te], (p_xs + p_ml) / 2)},
        "protein_context": {"xgboost": scores(y[te], p_xc), "keras_cnn": scores(y[te], p_cn),
                            "ensemble": scores(y[te], (p_xc + p_cn) / 2)},
        "xgboost_context_importance": {n: round(float(v), 4) for n, v in sorted(
            zip(names, xgb_ctx.feature_importances_), key=lambda t: -t[1])[:10]}}
    ART.mkdir(exist_ok=True)
    xgb_sub.save_model(ART / "xgb.json")
    mlp.save(ART / "mlp.keras")
    xgb_ctx.save_model(ART / "xgb_ctx.json")
    cnn.save(ART / "cnn_ctx.keras")
    (ART / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    main()
