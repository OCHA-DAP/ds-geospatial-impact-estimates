"""Ranking margin over the geography benchmark — the appendix replacement for the rq3f table.

One bar per product: its rank correlation minus the benchmark's, on identical cells. Zero is
the benchmark, so the sign is the finding and the length is how far off. Two panels, the two
frames the brief reports in.

The benchmark is a single score in the core region (one shared cell set) but a different score
per product as delivered (each product scored on its own footprint), which is why a margin
reads cleanly where a single reference line would not. Each row carries the product's own
correlation, so the absolute level is not lost.

Reads the same frozen CSVs as rq3f_null_ranking_both_fig.py; no refitting.

Run: uv run --with pandas --with matplotlib --with numpy python \
       exploratory/paper/pipeline/figs/rq3f_null_margin_fig.py
"""
from __future__ import annotations

import os

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "..", "figures")
os.makedirs(FIGS, exist_ok=True)

AHEAD, BEHIND = "#269777", "#c44536"          # HDX brand green / the null red used elsewhere
INK, MUTED = "#1f2324", "#5e6a6b"

asd = pd.read_csv(os.path.join(HERE, "..", "legacy", "rq3f_null_ranking.csv"))
core = pd.read_csv(os.path.join(HERE, "..", "legacy", "rq3f_null_ranking_core.csv"))

panels = [
    (asd[asd.res == 7], "As delivered", "each product's own footprint, ~5 km² sectors"),
    (core[core.res == 8], "Core region", "one shared cell set, ~0.7 km² cells"),
]

fig, axes = plt.subplots(1, 2, figsize=(14.5, 5.8), sharex=True)
for ax, (df, title, sub) in zip(axes, panels):
    s = df.sort_values("delta", ascending=False).reset_index(drop=True)
    margin = s.rho_product - s.rho_null
    y = np.arange(len(s))
    colours = [AHEAD if m > 0 else BEHIND for m in margin]
    ax.barh(y, margin, height=0.6, color=colours, zorder=3)

    for i, (m, r) in enumerate(zip(margin, s.itertuples())):
        inside = m < -0.55                      # a long bar keeps its label off the tick text
        if inside:
            ax.text(m + 0.02, i, f"{m:+.2f}", va="center", ha="left",
                    fontsize=10.5, weight="bold", color="#ffffff", zorder=4)
        else:
            off = 0.015 if m > 0 else -0.015
            ax.text(m + off, i, f"{m:+.2f}", va="center", ha="left" if m > 0 else "right",
                    fontsize=10.5, weight="bold", color=AHEAD if m > 0 else BEHIND, zorder=4)

    # product name carries its own correlation, so the margin never hides the level
    ax.set_yticks(y, [f"{r.product}   ρ {r.rho_product:.2f}" for r in s.itertuples()],
                  fontsize=11.5)
    n_ahead = int((margin > 0).sum())
    ax.set_title(f"{title}: {sub}\n"
                 f"products ranking better than geography: {n_ahead} of {len(s)}",
                 fontsize=11.5, loc="left", color=INK)

for ax in axes:
    ax.axvline(0, color=INK, lw=1.6, zorder=5)
    ax.set_xlim(-0.88, 0.24)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.22, zorder=0)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)

# name the zero line once, above the first bar, clear of the ticks
axes[0].text(0.012, -0.62, "geography benchmark", va="center", ha="left",
             fontsize=9.5, style="italic", color=MUTED, zorder=6)

fig.supxlabel("Rank correlation minus the geography benchmark's, on identical cells  "
              "(right of zero = the product ranks the worst-hit areas better)", fontsize=11.5)
fig.suptitle("Do the products rank areas better than geography alone?",
             fontsize=14, weight="bold", color=INK)
fig.tight_layout(rect=(0, 0.03, 1, 0.96))
out = os.path.join(FIGS, "rq3f_null_margin.png")
fig.savefig(out, dpi=150, bbox_inches="tight")
print("wrote", out)
