"""RQ3f figure — product vs geography area-ranking, distilled to one dumbbell plot.

Figure-only (reads the frozen rq3f CSVs, no recompute). Built for manuscript v3, where
it replaces the priority map and the two ranking tables in the main text (both retained
in the appendix). Panel A: pooled across all five mapped areas at the ~5 km² sector
scale (res 7), the task geography wins because it is mostly "find Caraballeda". Panel B:
within Caraballeda at ~0.7 km² (res 8), where the six split three-three.

Run: uv run --with pandas --with matplotlib python \
       exploratory/paper/artefacts/RQ3-prioritization-error-structure/scripts/rq3f_ranking_dumbbell_fig.py
"""
from __future__ import annotations

import os

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(HERE, "..", "figs")
os.makedirs(FIGS, exist_ok=True)

C_PROD, C_NULL = "#2a78d6", "#c0392b"   # validated pair (CVD-safe)

pooled = pd.read_csv(os.path.join(HERE, "..", "rq3f_null_ranking.csv"))
cara = pd.read_csv(os.path.join(HERE, "..", "rq3f_null_ranking_caraballeda.csv"))

panels = [
    (pooled[pooled.res == 7], "A · all five mapped areas, ~5 km² sectors",
     "mostly a test of finding Caraballeda"),
    (cara[cara.res == 8], "B · within Caraballeda, ~0.7 km² cells",
     "the within-zone test"),
]

fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6), sharex=True)
for ax, (d, title, sub) in zip(axes, panels):
    d = d.sort_values("rho_product").reset_index(drop=True)
    y = range(len(d))
    for i, r in d.iterrows():
        ax.plot([r.rho_null, r.rho_product], [i, i], color="#c9c9c9", lw=2, zorder=1)
    ax.scatter(d.rho_null, y, s=95, color=C_NULL, marker="D", zorder=3,
               label="geography null")
    ax.scatter(d.rho_product, y, s=110, color=C_PROD, zorder=4, label="product")
    ax.set_yticks(list(y))
    ax.set_yticklabels(d["product"], fontsize=11)
    ax.axvline(0, color="#999999", lw=0.8, ls=":")
    ax.set_title(f"{title}\n{sub}", fontsize=11, loc="left")
    ax.set_xlabel("rank correlation with expert damage count (ρ)", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", color="#eeeeee", lw=0.8)
    ax.set_axisbelow(True)

n_beat_a = int((panels[0][0].rho_product > panels[0][0].rho_null).sum())
n_beat_b = int((panels[1][0].rho_product > panels[1][0].rho_null).sum())
axes[0].annotate(f"geography ahead for {6 - n_beat_a} of 6", xy=(0.03, 0.96),
                 xycoords="axes fraction", ha="left", va="top", fontsize=10,
                 color=C_NULL, weight="bold")
axes[1].annotate(f"products ahead {n_beat_b}–{6 - n_beat_b}", xy=(0.03, 0.96),
                 xycoords="axes fraction", ha="left", va="top", fontsize=10,
                 color="#444444", weight="bold")

handles = [Line2D([], [], marker="o", ls="", ms=10, color=C_PROD, label="product"),
           Line2D([], [], marker="D", ls="", ms=9, color=C_NULL,
                  label="geography null (hindsight-fitted)")]
fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False, fontsize=10,
           bbox_to_anchor=(0.5, -0.02))
fig.suptitle("Who ranks the damage better: each product against a geography-only model",
             fontsize=12.5, x=0.5, y=0.99)
fig.tight_layout(rect=(0, 0.05, 1, 0.94))
out = os.path.join(FIGS, "rq3f_ranking_dumbbell.png")
fig.savefig(out, dpi=150, bbox_inches="tight")
print("wrote", out)
