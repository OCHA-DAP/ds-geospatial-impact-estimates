"""Draw the best-F1 comparison bar chart from the CSV rq8_learned_fusion.py already wrote.

Split out so the figure can be restyled without re-fitting the models (the parent script
reloads ~400k buildings from Azure and refits 5-fold CV, which takes minutes).

Run: uv run --with pandas --with matplotlib python \
       exploratory/paper/artefacts/RQ8-learned-fusion/scripts/rq8_best_f1_fig.py [radius]
     radius defaults to 10 (the paper's primary frame); pass 20 for the appendix version.
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
R = int(sys.argv[1]) if len(sys.argv) > 1 else 10
SUF = f"_r{R}"  # CSVs always carry an explicit radius suffix (renamed 2026-08-06)

df = pd.read_csv(os.path.join(HERE, "..", f"rq8_best_f1{SUF}.csv"))
prod = df[df.kind.str.startswith("product")].sort_values("f1")
ours = df[~df.kind.str.startswith("product")].sort_values("f1")

COL = {"geography null (logistic)": "#c44536", "geography null (rand. forest)": "#dc8f86",
       "flat k-of-6 voting": "#51ac92", "weighted fusion": "#18614c"}  # hdx error-5/3, brand-4/7
lab = [*prod.predictor, *ours.predictor]
val = [*prod.f1, *ours.f1]
cols = ["#9db1b3"] * len(prod) + [COL[n] for n in ours.predictor]
yp = np.arange(len(lab), dtype=float)
yp[len(prod):] += 0.6

fig, ax = plt.subplots(figsize=(11, 6.6))
ax.barh(yp, val, color=cols, zorder=2)
for yy, (_, row) in zip(yp, pd.concat([prod, ours]).iterrows()):
    ax.text(row.f1 + 0.004, yy, f"{row.f1:.3f}   (P {row.precision:.3f} / R {row.recall:.3f})",
            va="center", fontsize=10.5)
ax.set_yticks(yp, lab, fontsize=12)
ax.set_xlim(0, max(val) * 1.45)
ax.set_ylim(-0.8, max(yp) + 0.8)
ax.set_xlabel(f"F1 at the operating point (CEMS {{2,3}} within {R} m)", fontsize=12)
ax.set_title("Like-for-like: each product at the ONE point it shipped,\n"
             "against our scores at their best single cut", fontsize=13)
# footnote below the axes, so it cannot collide with the bar annotations
fig.text(0.99, 0.015,
         "grey = provider's own threshold  ·  coloured = best single cut of our score      "
         "primary null = logistic; the paler forest null is the weaker learner, kept for robustness",
         ha="right", fontsize=9, style="italic", color="#5a6570")
fig.tight_layout(rect=(0, 0.045, 1, 1))
out = os.path.join(FIGS, f"rq8_best_f1{SUF}.png")
fig.savefig(out, dpi=150)
print(f"wrote {os.path.relpath(out, HERE)}")
