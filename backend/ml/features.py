"""Substitution-level features for a missense change. Pure python/numpy, no ML framework needed."""
from __future__ import annotations

import re

import numpy as np

AA = "ARNDCQEGHILKMFPSTWYV"
THREE = {"Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q", "Glu": "E", "Gly": "G", "His": "H",
         "Ile": "I", "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S", "Thr": "T", "Trp": "W",
         "Tyr": "Y", "Val": "V"}

_BLOSUM_TXT = """
   A  R  N  D  C  Q  E  G  H  I  L  K  M  F  P  S  T  W  Y  V
A  4 -1 -2 -2  0 -1 -1  0 -2 -1 -1 -1 -1 -2 -1  1  0 -3 -2  0
R -1  5  0 -2 -3  1  0 -2  0 -3 -2  2 -1 -3 -2 -1 -1 -3 -2 -3
N -2  0  6  1 -3  0  0  0  1 -3 -3  0 -2 -3 -2  1  0 -4 -2 -3
D -2 -2  1  6 -3  0  2 -1 -1 -3 -4 -1 -3 -3 -1  0 -1 -4 -3 -3
C  0 -3 -3 -3  9 -3 -4 -3 -3 -1 -1 -3 -1 -2 -3 -1 -1 -2 -2 -1
Q -1  1  0  0 -3  5  2 -2  0 -3 -2  1  0 -3 -1  0 -1 -2 -1 -2
E -1  0  0  2 -4  2  5 -2  0 -3 -3  1 -2 -3 -1  0 -1 -3 -2 -2
G  0 -2  0 -1 -3 -2 -2  6 -2 -4 -4 -2 -3 -3 -2  0 -2 -2 -3 -3
H -2  0  1 -1 -3  0  0 -2  8 -3 -3 -1 -2 -1 -2 -1 -2 -2  2 -3
I -1 -3 -3 -3 -1 -3 -3 -4 -3  4  2 -3  1  0 -3 -2 -1 -3 -1  3
L -1 -2 -3 -4 -1 -2 -3 -4 -3  2  4 -2  2  0 -3 -2 -1 -2 -1  1
K -1  2  0 -1 -3  1  1 -2 -1 -3 -2  5 -1 -3 -1  0 -1 -3 -2 -2
M -1 -1 -2 -3 -1  0 -2 -3 -2  1  2 -1  5  0 -2 -1 -1 -1 -1  1
F -2 -3 -3 -3 -2 -3 -3 -3 -1  0  0 -3  0  6 -4 -2 -2  1  3 -1
P -1 -2 -2 -1 -3 -1 -1 -2 -2 -3 -3 -1 -2 -4  7 -1 -1 -4 -3 -2
S  1 -1  1  0 -1  0  0  0 -1 -2 -2  0 -1 -2 -1  4  1 -3 -2 -2
T  0 -1  0 -1 -1 -1 -1 -2 -2 -1 -1 -1 -1 -2 -1  1  5 -2 -2  0
W -3 -3 -4 -4 -2 -2 -3 -2 -2 -3 -2 -3 -1  1 -4 -3 -2 11  2 -3
Y -2 -2 -2 -3 -2 -1 -2 -3  2 -1 -1 -2 -1  3 -3 -2 -2  2  7 -1
V  0 -3 -3 -3 -1 -2 -2 -3 -3  3  1 -2  1 -1 -2 -2  0 -3 -1  4
"""
_rows = [r.split() for r in _BLOSUM_TXT.strip().splitlines()]
_cols = _rows[0]
BLOSUM = {(r[0], c): int(v) for r in _rows[1:] for c, v in zip(_cols, r[1:])}

# Kyte-Doolittle hydropathy, side-chain volume (A^3), charge at pH 7, polarity (Grantham), aromatic
KD = dict(zip(AA, [1.8, -4.5, -3.5, -3.5, 2.5, -3.5, -3.5, -0.4, -3.2, 4.5, 3.8, -3.9, 1.9, 2.8,
                   -1.6, -0.8, -0.7, -0.9, -1.3, 4.2]))
VOL = dict(zip(AA, [88.6, 173.4, 114.1, 111.1, 108.5, 143.8, 138.4, 60.1, 153.2, 166.7, 166.7, 168.6,
                    162.9, 189.9, 112.7, 89.0, 116.1, 227.8, 193.6, 140.0]))
CHG = {a: 0.0 for a in AA}
CHG.update({"K": 1.0, "R": 1.0, "H": 0.1, "D": -1.0, "E": -1.0})
POL = dict(zip(AA, [8.1, 10.5, 11.6, 13.0, 5.5, 10.5, 12.3, 9.0, 10.4, 5.2, 4.9, 11.3, 5.7, 5.2,
                    8.0, 9.2, 8.6, 5.4, 6.2, 5.9]))
AROM = {a: float(a in "FWYH") for a in AA}

FEATURE_NAMES = ["ref_idx", "alt_idx", "blosum", "d_hydro", "d_volume", "d_charge", "d_polarity", "ref_hydro", "ref_volume",
                 "ref_polarity", "ref_charge", "alt_hydro", "alt_volume", "alt_polarity", "alt_charge", "ref_arom", "alt_arom",
                 "to_pro", "from_pro", "to_gly", "from_gly", "from_cys", "to_cys", "log_pos"]

_HGVS = re.compile(r"^(?:p\.)?([A-Z][a-z]{2}|[A-Z])(\d+)([A-Z][a-z]{2}|[A-Z])$")


def parse_change(change: str) -> tuple[str, int, str]:
    """'p.Arg52His' | 'R52H' -> ('R', 52, 'H'). Raises ValueError for anything that is not a plain missense."""
    m = _HGVS.match(change.strip())
    if not m:
        raise ValueError(f"not a missense change: {change!r}")
    ref, pos, alt = m.groups()
    ref, alt = THREE.get(ref, ref), THREE.get(alt, alt)
    if ref not in AA or alt not in AA or ref == alt:
        raise ValueError(f"not a missense change: {change!r}")
    return ref, int(pos), alt


def featurize(ref: str, pos: int, alt: str) -> list[float]:
    return [AA.index(ref), AA.index(alt), BLOSUM[(ref, alt)], KD[alt] - KD[ref], VOL[alt] - VOL[ref], CHG[alt] - CHG[ref],
            POL[alt] - POL[ref], KD[ref], VOL[ref], POL[ref], CHG[ref], KD[alt], VOL[alt], POL[alt], CHG[alt], AROM[ref],
            AROM[alt], float(alt == "P"), float(ref == "P"), float(alt == "G"), float(ref == "G"), float(ref == "C"),
            float(alt == "C"), float(np.log1p(pos))]


def featurize_many(changes: list[tuple[str, int, str]]) -> np.ndarray:
    return np.asarray([featurize(*c) for c in changes], dtype=np.float32)


# --- protein-context features (need the wild-type sequence) -------------------------------------------------------
WIN = 15                                     # CNN half-window: 31 residues centred on the variant
CTX_NAMES = ["rel_pos", "log_len", "dist_term", "kd_w3", "kd_w7", "kd_w15", "chg_w7", "vol_w7", "kd_m2", "kd_m1", "kd_p1",
             "kd_p2", "gp_frac_w7", "chg_frac_w7", "cys_frac_w7", "entropy_w10", "same_aa_w7", "max_tm_kd19",
             "ref_frac_protein", "cys_frac_protein", "is_n_signal"]


def _win(seq: str, pos: int, half: int) -> str:
    return seq[max(0, pos - 1 - half): pos + half]


def _mean(table: dict, s: str) -> float:
    return float(np.mean([table.get(c, 0.0) for c in s])) if s else 0.0


def _entropy(s: str) -> float:
    if not s:
        return 0.0
    p = np.array([s.count(a) for a in set(s)], dtype=float) / len(s)
    return float(-(p * np.log2(p)).sum())


def context_features(ref: str, pos: int, seq: str) -> list[float]:
    n, i = len(seq), pos - 1
    at = lambda k: KD.get(seq[i + k], 0.0) if 0 <= i + k < n else 0.0
    w7, w10 = _win(seq, pos, 7), _win(seq, pos, 10)
    tm = max((_mean(KD, seq[a:a + 19]) for a in range(max(0, i - 18), min(i, max(0, n - 19)) + 1)), default=0.0)
    return [pos / n, float(np.log(n)), float(min(pos - 1, n - pos)), _mean(KD, _win(seq, pos, 3)), _mean(KD, w7),
            _mean(KD, _win(seq, pos, 15)), _mean(CHG, w7), _mean(VOL, w7), at(-2), at(-1), at(1), at(2),
            sum(c in "GP" for c in w7) / len(w7), sum(c in "KRDE" for c in w7) / len(w7), w7.count("C") / len(w7),
            _entropy(w10), w7.count(ref) / len(w7), tm, seq.count(ref) / n, seq.count("C") / n,
            float(pos <= 30 and _mean(KD, seq[:30]) > 1.0)]


def window_onehot(seq: str, pos: int, half: int = WIN) -> np.ndarray:
    out = np.zeros((2 * half + 1, len(AA)), dtype=np.float32)
    for k in range(-half, half + 1):
        j = pos - 1 + k
        if 0 <= j < len(seq) and seq[j] in AA:
            out[k + half, AA.index(seq[j])] = 1.0
    return out


def featurize_ctx(ref: str, pos: int, alt: str, seq: str) -> tuple[list[float], np.ndarray]:
    """-> (tabular vector = substitution + context features, one-hot window). Raises if seq[pos-1] != ref."""
    if not (1 <= pos <= len(seq)) or seq[pos - 1] != ref:
        raise ValueError(f"reference residue {ref}{pos} does not match the sequence")
    return featurize(ref, pos, alt) + context_features(ref, pos, seq), window_onehot(seq, pos)
