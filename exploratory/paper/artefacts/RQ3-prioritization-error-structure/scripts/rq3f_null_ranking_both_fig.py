"""RQ3f figure for manuscript v3 — BOTH ranking tests, same style as the deck figure.

Panel A: all five mapped areas, each product's own footprint, ~5 km² sectors (res 7) —
the deck's single-panel test. Panel B: cells inside Caraballeda only, ~0.7 km² (res 8) —
the within-zone test, where the six split against the model. Reads the two frozen rq3f
CSVs; no refitting. Style follows rq3f_null_ranking_fig.py (HDX v2 tokens).

Run: uv run --with pandas --with matplotlib --with numpy python \
       exploratory/paper/artefacts/RQ3-prioritization-error-structure/scripts/rq3f_null_ranking_both_fig.py
"""
from __future__ import annotations

import os

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
os.makedirs(FIGS, exist_ok=True)

PROD, NULL = "#3f4748", "#c44536"

pooled = pd.read_csv(os.path.join(HERE, "..", "rq3f_null_ranking.csv"))
core = pd.read_csv(os.path.join(HERE, "..", "rq3f_null_ranking_core.csv"))

fig, axes = plt.subplots(1, 2, figsize=(14.5, 6.2), sharex=True)

# Panel A — as-delivered lens: each product's own footprint, null re-scored per row.
sA = pooled[pooled.res == 7].sort_values("rho_product", ascending=False).reset_index(drop=True)
ax = axes[0]
yA = np.arange(len(sA)); h = 0.37
ax.barh(yA - h / 2, sA.rho_product, height=h, color=PROD, zorder=3)
ax.barh(yA + h / 2, sA.rho_null, height=h, color=NULL, zorder=3)
for i, r in sA.iterrows():
    ax.text(max(r.rho_product, 0) + 0.012, i - h / 2, f"{r.rho_product:.2f}",
            va="center", fontsize=10.5, color=PROD, weight="bold")
    ax.text(r.rho_null + 0.012, i + h / 2, f"{r.rho_null:.2f}",
            va="center", fontsize=10.5, color=NULL, weight="bold")
    ax.text(0.99, i, "product" if r.rho_product > r.rho_null else "null",
            transform=ax.get_yaxis_transform(), ha="right", va="center",
            fontsize=9.5, style="italic",
            color=PROD if r.rho_product > r.rho_null else NULL, zorder=5)
n_null = int((sA.rho_null > sA.rho_product).sum())
ax.set_yticks(yA, sA["product"], fontsize=11.5)
ax.set_title("Test 1 · as delivered: each product's own footprint, ~5 km² sectors\n"
             "(geography re-scored on each product's cells; ahead for "
             f"{n_null} of {len(sA)})", fontsize=11.5, loc="left", color="#1f2324")

# Panel B — core lens: one shared cell set, so geography has a single score.
sB = core[core.res == 8].sort_values("rho_product", ascending=False).reset_index(drop=True)
nulls = sB.rho_null.unique()
assert len(nulls) == 1, f"core null should be single-valued, got {nulls}"
null_v = float(nulls[0])
ax = axes[1]
yB = np.arange(len(sB))
ax.barh(yB, sB.rho_product, height=0.55, color=PROD, zorder=3)
for i, r in sB.iterrows():
    ax.text(max(r.rho_product, 0) + 0.012, i, f"{r.rho_product:.2f}",
            va="center", fontsize=10.5, color=PROD, weight="bold")
ax.axvline(null_v, color=NULL, lw=2.5, zorder=4)
ax.text(null_v + 0.015, len(sB) - 0.55, f"geography null {null_v:.2f}", color=NULL,
        fontsize=11, weight="bold", ha="left", va="center")
n_above = int((sB.rho_product > null_v).sum())
ax.set_yticks(yB, sB["product"], fontsize=11.5)
ax.set_title("Test 2 · core region: one shared cell set, ~0.7 km² cells\n"
             f"(geography has a single score; products above it: {n_above} of {len(sB)})",
             fontsize=11.5, loc="left", color="#1f2324")

for ax in axes:
    ax.axvline(0, color="#5e6a6b", lw=1, zorder=4)
    ax.set_xlim(-0.18, 0.92)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.25, zorder=0)
    ax.spines[["top", "right", "left"]].set_visible(False)

fig.supxlabel("Spearman rank correlation with the expert damage count per cell  "
              "(higher = ranks the worst-hit areas better)", fontsize=11.5)
h1 = plt.Rectangle((0, 0), 1, 1, color=PROD)
h2 = plt.Rectangle((0, 0), 1, 1, color=NULL)
fig.legend([h1, h2], ["satellite product",
                      "geography null (coast distance + building density + shaking)"],
           loc="lower center", ncol=2, fontsize=11, frameon=False,
           bbox_to_anchor=(0.5, -0.04))
fig.suptitle("Ranking which areas were worst hit: the two tests", fontsize=14,
             weight="bold", color="#1f2324")
fig.tight_layout(rect=(0, 0.03, 1, 0.97))
out = os.path.join(FIGS, "rq3f_null_ranking_both.png")
fig.savefig(out, dpi=150, bbox_inches="tight")
print("wrote", out)
