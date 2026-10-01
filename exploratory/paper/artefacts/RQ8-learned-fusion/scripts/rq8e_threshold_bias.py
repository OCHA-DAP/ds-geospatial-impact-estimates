"""RQ8e — does choosing the cutoff with hindsight flatter our scores? Nested check for the
geography null, the weighted fusion AND flat voting, treated identically.

Background. A shipped product is one operating point. Our continuous scores (null, fusion) and
the vote count are cut at the threshold that maximises F1 on the pooled out-of-fold scores —
one parameter chosen with knowledge of every label (rq8_best_f1_r10.csv, "our score @ its best
single cut"). rq8_learned_fusion.py already ran a nested check for the NULL (refit an inner
model, pick the cut on inner validation): F1 0.1712 nested vs 0.172 hindsight. It never ran it
for the fusion, whose 15 inputs leave more room for a flattering cut (Tristan, 2026-09-09).

Method here (needs no refitting, so it treats all three scores the same way): rebuild the five
spatial folds exactly as rq8 did (GroupKFold on the H3 res-7 cell of each building), and for
each outer fold pick the F1-maximising threshold on the TRAINING folds' out-of-fold scores, then
apply it blind to the test fold. Pool the five test folds into one P/R/F1. The hindsight row is
best_f1 over all scores at once (reproduces rq8_best_f1_r10.csv). "nested - hindsight" is the
selection effect; a small gap means the headline numbers are not an artefact of the cut.

Input: rq8_oof_scores_r10.parquet (heavy output of rq8, gitignored). Output:
rq8e_threshold_bias_r10.csv — signed off into frozen/ via MANIFEST.csv (ADR-0032).
Run: uv run --group etl python exploratory/paper/artefacts/RQ8-learned-fusion/scripts/rq8e_threshold_bias.py
"""
from __future__ import annotations
import os
import h3
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve
from sklearn.model_selection import GroupKFold

HERE = os.path.dirname(os.path.abspath(__file__))
R = int(os.environ.get("GIE_LABEL_R", "10"))
SUF = f"_r{R}"
FLAGS = ["flag_MS", "flag_IMPACT", "flag_OSU", "flag_UH", "flag_LIST", "flag_UNEP"]
SCORES = {"geography null (logistic)": "null_logit", "weighted fusion": "fusion_logit", "flat k-of-6 voting": "votes"}


def prf(sel: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    tp = int((sel & (y == 1)).sum()); fp = int((sel & (y == 0)).sum()); fn = int((~sel & (y == 1)).sum())
    p = tp / max(tp + fp, 1); r = tp / max(tp + fn, 1)
    return p, r, (2 * p * r / (p + r) if (p + r) > 0 else 0.0)


def best_threshold(y: np.ndarray, s: np.ndarray) -> float:
    """The F1-maximising cut, as rq8_learned_fusion.best_f1 defines it (>= threshold flags)."""
    p, r, thr = precision_recall_curve(y, s)
    f1 = np.divide(2 * p * r, p + r, out=np.zeros_like(p), where=(p + r) > 0)
    i = int(np.argmax(f1))
    return float(thr[i] if i < len(thr) else thr[-1])


def main():
    src = os.path.join(HERE, "..", f"rq8_oof_scores{SUF}.parquet")
    if not os.path.exists(src):
        raise FileNotFoundError(f"{src} missing: it is the heavy output of `snakemake rq8` (gitignored); run that first")
    d = pd.read_parquet(src)
    d["votes"] = d[FLAGS].sum(axis=1)
    y = d.y.to_numpy()
    groups = np.array([h3.latlng_to_cell(la, lo, 7) for la, lo in zip(d.lat, d.lon)])
    folds = list(GroupKFold(n_splits=5).split(d, y, groups))
    print(f"{len(d)} buildings, {int(y.sum())} positives, {len(set(groups))} res-7 blocks, {len(folds)} folds")

    rows = []
    for name, col in SCORES.items():
        s = d[col].to_numpy(dtype="float64")
        # hindsight: one cut on the pooled out-of-fold scores (what the brief quotes today)
        t_h = best_threshold(y, s)
        p_h, r_h, f_h = prf(s >= t_h, y)
        # nested: cut chosen on the training folds' scores, applied blind to the test fold
        sel = np.zeros(len(d), dtype=bool); chosen = []
        for tr, te in folds:
            t = best_threshold(y[tr], s[tr]); chosen.append(t)
            sel[te] = s[te] >= t
        p_n, r_n, f_n = prf(sel, y)
        rows.append(dict(predictor=name, method="hindsight, one global cut on all scores", precision=round(p_h, 4), recall=round(r_h, 4), f1=round(f_h, 4),
                         n_flags=int((s >= t_h).sum()), threshold=round(t_h, 4)))
        rows.append(dict(predictor=name, method="nested, per-fold cut chosen on training folds", precision=round(p_n, 4), recall=round(r_n, 4), f1=round(f_n, 4),
                         n_flags=int(sel.sum()), threshold=np.nan))
        rows.append(dict(predictor=name, method="difference (nested - hindsight)", precision=round(p_n - p_h, 4), recall=round(r_n - r_h, 4), f1=round(f_n - f_h, 4),
                         n_flags=int(sel.sum()) - int((s >= t_h).sum()), threshold=np.nan))
        print(f"{name:28s} hindsight F1 {f_h:.3f} (cut {t_h:.3f}) | nested F1 {f_n:.3f} (cuts {', '.join(f'{t:.3f}' for t in chosen)}) | Δ {f_n - f_h:+.4f}")

    out = os.path.join(HERE, "..", f"rq8e_threshold_bias{SUF}.csv")
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"wrote {os.path.relpath(out)}")


if __name__ == "__main__":
    main()
