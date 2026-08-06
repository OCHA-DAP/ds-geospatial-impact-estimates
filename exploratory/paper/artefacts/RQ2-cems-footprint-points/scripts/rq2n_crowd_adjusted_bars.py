"""RQ2n — as-delivered precision: strict CEMS floor vs MapSwipe crowd-adjusted (appendix).

Companion to the "benchmark" slide, answering "isn't it less bad if we credit damage the
expert missed?" Yes — crowd-confirmed damage lifts every product's as-delivered precision
~2-3x above the strict CEMS floor. Two honesty guards baked in:
  (1) crowd coverage is annotated — MS's boost rests on 98% of its flags being crowd-voted,
      UH's on just 2% (its dead-zone flags have no crowd votes), so not all boosts are equal;
  (2) we do NOT overlay the day-zero baseline here: MapSwipe only voted on AI-FLAGGED
      locations, so crediting it cannot fairly score the baseline — that comparison would be
      circular. This slide is about precision floors→intervals, not beating the baseline.

Reads rq2i_per_aoi_scorecard.csv (no compute).

Run: uv run --with pandas --with matplotlib python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2n_crowd_adjusted_bars.py
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
a = pd.read_csv(os.path.join(HERE, "..", "rq2i_per_aoi_scorecard.csv"))
a = a[a.aoi == "ALL (as delivered)"].set_index("product")
order = ["UH", "UNEP", "LIST", "IMPACT", "OSU", "MS"]  # MS at top; legend drops into UH corner

y = np.arange(len(order))
h = 0.36
fig, ax = plt.subplots(figsize=(12.5, 6.8))
for yi, p in zip(y, order):
    pc, pa, cov = a.loc[p, "P_cems"], a.loc[p, "P_crowd_adj"], a.loc[p, "crowd_cov_of_fps"]
    ax.barh(yi + h/2, pc, height=h, color="#8a5a00",
            label="strict — Copernicus expert only" if p == order[0] else None)
    ax.barh(yi - h/2, pa, height=h, color="#2a78d6",
            label="crowd-adjusted — + MapSwipe-confirmed damage" if p == order[0] else None)
    ax.text(pc + 0.003, yi + h/2, f"{pc:.3f}", va="center", fontsize=10.5, color="#8a5a00")
    ax.text(pa + 0.003, yi - h/2, f"{pa:.3f}  ({pa/pc:.1f}×)", va="center", fontsize=10.5,
            color="#1b4f8a", weight="bold")
    ax.text(-0.004, yi, p, va="center", ha="right", fontsize=14, weight="bold")
    tag = "well-supported" if cov > 0.6 else ("partial" if cov > 0.15 else "THIN — extrapolated")
    ax.text(0.30, yi, f"crowd saw {cov:.0%} of its flags · {tag}", va="center",
            fontsize=9, color="#666" if cov > 0.15 else "#c62828", style="italic")

ax.set_yticks([])
ax.set_xlim(0, 0.50)
ax.set_xlabel("as-delivered precision  (target: damaged OR destroyed buildings)", fontsize=12)
ax.tick_params(axis="x", labelsize=11)
ax.legend(fontsize=11.5, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2,
          frameon=False)
ax.set_title("The strict numbers are floors — crediting crowd-confirmed damage lifts them ~2–3×\n"
             "(but only where the crowd actually looked; and this can't fairly be compared to "
             "the no-satellite baseline — see note)", fontsize=12)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(os.path.join(FIGS, "rq2n_crowd_adjusted_bars.png"), dpi=150)
print("wrote rq2n_crowd_adjusted_bars.png")
