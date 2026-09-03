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
args = sys.argv[1:]
SLIDES = "--slides" in args  # deck variant: no reading-notes footnote (spoken instead)
# --summary: the technical-brief variant (ADR-0029) — no geography nulls, so the figure
# carries products + flat voting + weighted fusion only. Writes *_summary.png beside the
# unchanged default output; the v3 figure is never overwritten.
SUMMARY = "--summary" in args
nums = [a for a in args if a.isdigit()]
R = int(nums[0]) if nums else 10
SUF = f"_r{R}"  # CSVs always carry an explicit radius suffix (renamed 2026-08-06)

df = pd.read_csv(os.path.join(HERE, "..", f"rq8_best_f1{SUF}.csv"))
if SUMMARY:
    # The brief's figure: two panels, core (products + the two combined constructions,
    # no nulls) beside as-delivered (products only — the combinations are defined on the
    # shared footprint base and exist only in the core region). Reads the frozen rq8 and
    # rq8b CSVs; writes its own *_summary.png and exits before the single-panel path.
    df = df[~df.predictor.str.startswith("geography null")]
    prod = df[df.kind.str.startswith("product")].sort_values("f1")
    ours = df[~df.kind.str.startswith("product")].sort_values("f1")
    asd = pd.read_csv(os.path.join(HERE, "..", f"rq8b_asdelivered_baseline{SUF}.csv"))
    asd["f1"] = 2 * asd.P_product * asd.R_product / (asd.P_product + asd.R_product)
    asd = asd.sort_values("f1")
    NAMES = {"MS": "MS", "IMPACT": "IMPACT", "OSU": "OSU", "UH": "UH",
             "LIST": "LIST", "UNEP": "UNEP"}

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(15, 6.6))
    # left: core
    labL = [*prod.predictor, *ours.predictor]
    valL = [*prod.f1, *ours.f1]
    COLS = {"flat k-of-6 voting": "#51ac92", "weighted fusion": "#18614c"}
    colL = ["#9db1b3"] * len(prod) + [COLS[n] for n in ours.predictor]
    ypL = np.arange(len(labL), dtype=float)
    ypL[len(prod):] += 0.6
    axL.barh(ypL, valL, color=colL, zorder=2)
    for yy, (_, row) in zip(ypL, pd.concat([prod, ours]).iterrows()):
        axL.text(row.f1 + 0.004, yy, f"{row.f1:.3f}  (P {row.precision:.3f} / R {row.recall:.3f})",
                 va="center", fontsize=9.5)
    axL.set_yticks(ypL, labL, fontsize=11)
    axL.set_title("core region (61 km²)", fontsize=12, weight="bold")
    # right: as delivered, products only
    ypR = np.arange(len(asd), dtype=float)
    axR.barh(ypR, asd.f1, color="#9db1b3", zorder=2)
    for yy, (_, row) in zip(ypR, asd.iterrows()):
        axR.text(row.f1 + 0.004, yy,
                 f"{row.f1:.3f}  (P {row.P_product:.3f} / R {row.R_product:.3f})",
                 va="center", fontsize=9.5)
    axR.set_yticks(ypR, [NAMES[p_] for p_ in asd["product"]], fontsize=11)
    axR.set_title("as delivered (products only)", fontsize=12, weight="bold")
    xmax = max(max(valL), float(asd.f1.max())) * 1.55
    for ax in (axL, axR):
        ax.set_xlim(0, xmax)
        ax.set_xlabel(f"F1 at the operating point (CEMS damaged/destroyed within {R} m)",
                      fontsize=11)
        ax.spines[["top", "right"]].set_visible(False)
    axL.set_ylim(-0.8, max(ypL) + 0.8)
    axR.set_ylim(-0.8, max(ypL) + 0.8)  # same vertical scale so the panels read together
    fig.suptitle("Product & combined product performance (F1/P/R)", fontsize=14)
    fig.text(0.99, 0.015,
             "grey = provider's own threshold  ·  green = combined products at their best single cut "
             "(defined on the shared footprint base: core region only)",
             ha="right", fontsize=9, style="italic", color="#5a6570")
    fig.tight_layout(rect=(0, 0.045, 1, 0.95))
    out = os.path.join(FIGS, f"rq8_best_f1{SUF}_summary.png")
    fig.savefig(out, dpi=150)
    print(f"wrote {os.path.relpath(out, HERE)}")
    raise SystemExit(0)

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
if SLIDES:
    fig.tight_layout()
elif SUMMARY:
    fig.text(0.99, 0.015,
             "grey = provider's own threshold  ·  coloured = best single cut of the combined score",
             ha="right", fontsize=9, style="italic", color="#5a6570")
    fig.tight_layout(rect=(0, 0.045, 1, 1))
else:
    # footnote below the axes, so it cannot collide with the bar annotations
    fig.text(0.99, 0.015,
             "grey = provider's own threshold  ·  coloured = best single cut of our score      "
             "primary null = logistic; the paler forest null is the weaker learner, kept for robustness",
             ha="right", fontsize=9, style="italic", color="#5a6570")
    fig.tight_layout(rect=(0, 0.045, 1, 1))
out = os.path.join(FIGS, f"rq8_best_f1{SUF}{'_slides' if SLIDES else '_summary' if SUMMARY else ''}.png")
fig.savefig(out, dpi=150)
print(f"wrote {os.path.relpath(out, HERE)}")
