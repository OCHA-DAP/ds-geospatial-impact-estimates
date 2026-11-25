"""Main-text best-F1 chart, counted the way every other main-text number is counted.

The earlier chart (rq8_best_f1_fig.py --summary) scored products in the building-label frame,
because it set them beside the weighted fusion, a model that can only be scored on a yes/no
label per building. That put a second recall for each product into the main text beside
Table 3's. This version uses the points frame throughout: recall is the share of CEMS damage
points with a flag within 10 m, as in Table 3 and the agreement dial. The fusion is left out
(the main text carries it as a ratio in prose); the combined bar is the best of the six
agreement rules.

Reads results.csv through brief_numbers (rq5b = core, points lens; asd = as delivered).
As-delivered rows carry no F1, so it is derived from P and R with the standard formula,
which reproduces the pipeline's own core-region F1 exactly.

Run from the repo root:
  uv run --group etl --with matplotlib python exploratory/paper/pipeline/figs/best_f1_points_fig.py
"""
from __future__ import annotations

import os
import sys

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.join(HERE, "..", "..")
sys.path.insert(0, PAPER)
from brief_numbers import rq5b, asd, PRODUCTS  # noqa: E402

FIGS = os.path.join(PAPER, "figures")
NAME = {"MS": "Microsoft", "IMPACT": "IMPACT v2", "OSU": "OSU", "UH": "UH",
        "LIST": "LIST", "UNEP": "UNEP"}
GREY, GREEN = "#9db1b3", "#51ac92"


def f1(p, r):
    return 2 * p * r / (p + r)


core = rq5b[10]
prod = core.loc[PRODUCTS, ["P_cems", "R_cems", "F1_cems"]].sort_values("F1_cems")
rules = core.loc[[f"{k}-of-6" for k in range(1, 7)], ["P_cems", "R_cems", "F1_cems"]]
best_k = rules.F1_cems.idxmax()
best = rules.loc[best_k]
if abs(f1(prod.loc["MS", "P_cems"], prod.loc["MS", "R_cems"]) - prod.loc["MS", "F1_cems"]) > 0.0015:
    raise SystemExit("derived F1 does not reproduce the pipeline's core F1; check the formula")

ad = asd.loc[PRODUCTS, ["P_cems", "R_cems"]].copy()
ad["F1"] = f1(ad.P_cems, ad.R_cems)
ad = ad.sort_values("F1")

fig, (axL, axR) = plt.subplots(1, 2, figsize=(15, 6.2))

# left: core region, products then the best agreement rule
labL = [NAME[p] for p in prod.index] + [f"{best_k} agreement (best rule)"]
valL = [*prod.F1_cems, best.F1_cems]
PRL = [*zip(prod.P_cems, prod.R_cems), (best.P_cems, best.R_cems)]
ypL = np.arange(len(labL), dtype=float)
ypL[-1] += 0.6
axL.barh(ypL, valL, color=[GREY] * len(prod) + [GREEN], zorder=2)
for yy, v, (p, r) in zip(ypL, valL, PRL):
    axL.text(v + 0.004, yy, f"{v:.3f}  (P {p:.3f} / R {r:.3f})", va="center", fontsize=9.5)
axL.set_yticks(ypL, labL, fontsize=11)
axL.set_title("core region", fontsize=12, weight="bold")

# right: as delivered, products only
ypR = np.arange(len(ad), dtype=float)
axR.barh(ypR, ad.F1, color=GREY, zorder=2)
for yy, (_, row) in zip(ypR, ad.iterrows()):
    axR.text(row.F1 + 0.004, yy, f"{row.F1:.3f}  (P {row.P_cems:.3f} / R {row.R_cems:.3f})",
             va="center", fontsize=9.5)
axR.set_yticks(ypR, [NAME[p] for p in ad.index], fontsize=11)
axR.set_title("as delivered (products only)", fontsize=12, weight="bold")

xmax = max(max(valL), float(ad.F1.max())) * 1.55
for ax in (axL, axR):
    ax.set_xlim(0, xmax)
    ax.set_xlabel("F1 score", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylim(-0.8, max(ypL) + 0.8)
fig.suptitle("Product and combined-product performance (F1, precision, recall)", fontsize=14)
fig.text(0.99, 0.015,
         "grey = provider's own threshold  ·  green = the best of the six agreement rules "
         "(core region only)  ·  recall = share of CEMS damage points found",
         ha="right", fontsize=9, style="italic", color="#5a6570")
fig.tight_layout(rect=(0, 0.045, 1, 0.95))
out = os.path.join(FIGS, "best_f1_points_r10.png")
fig.savefig(out, dpi=150)
print("wrote", os.path.relpath(out), "| best rule:", best_k, round(best.F1_cems, 3))
