"""RQ3h companion figure — the k-of-6 dial ranks the core region (both metrics apart).

2x2: columns are the two cell scales, rows are the two questions —
Spearman rho (trust the FULL ordering) and tie-aware expected top-20 overlap
(did the 20 worst cells make the shortlist). Singles, the geography null and
weighted fusion are reference lines, all labelled in one dodged stack at the
right edge so nothing sits on the data.

Reads rq3h_agreement_ranking.csv (no compute).

Run: uv run --with pandas --with matplotlib python \
       exploratory/paper/artefacts/RQ3-prioritization-error-structure/scripts/rq3h_agreement_ranking_fig.py
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
df = pd.read_csv(os.path.join(HERE, "..", "rq3h_agreement_ranking.csv"))
SINGLES = ["Microsoft", "IMPACT v2", "OSU", "UH", "LIST", "UNEP"]
KS = np.arange(1, 7)

fig, axes = plt.subplots(2, 2, figsize=(13.5, 10.5), sharex=True)
for col, res in enumerate((8, 9)):
    v = df[df.res == res].set_index("predictor")
    for row, (metric, mlab) in enumerate((
            ("rho", "Spearman ρ — how well the FULL cell ordering matches CEMS"),
            ("top20_exp", "top-20 overlap — share of the 20 worst-hit cells shortlisted\n"
                          "(tie-aware expected value)"))):
        ax = axes[row][col]
        # every reference line labelled at the right edge, one dodged stack
        refs = [(v.loc[s, metric], s, "#9db1b3", "#5a6570", 1.1, "-") for s in SINGLES]
        refs.append((v.loc["geography null", metric], "geography null",
                     "#c44536", "#c44536", 2.0, (0, (4, 3))))
        refs.append((v.loc["weighted fusion", metric], "weighted fusion",
                     "#1b4f8a", "#1b4f8a", 1.6, ":"))
        refs.sort(key=lambda t: t[0])
        min_gap = 0.04
        ys = []
        for val, *_ in refs:
            yy = val
            if ys and yy - ys[-1] < min_gap:
                yy = ys[-1] + min_gap
            ys.append(yy)
        for (val, nm, lc, tc, lw, ls), yy in zip(refs, ys):
            ax.axhline(val, color=lc, lw=lw, ls=ls, zorder=2 if lw > 1.2 else 1)
            ax.annotate(f"{nm}  {val:.2f}", (6.35, val), xytext=(6.6, yy),
                        textcoords="data", fontsize=8.5, color=tc, va="center",
                        weight="bold" if lw > 1.2 else "normal",
                        arrowprops=dict(arrowstyle="-", color=lc, lw=0.5, alpha=0.6))
        # the dial, values above every point
        vals = [v.loc[f"{k}-of-6", metric] for k in KS]
        ax.plot(KS, vals, marker="o", ms=8, lw=2.6, color="#18614c", zorder=3)
        for k, val in zip(KS, vals):
            ax.annotate(f"{val:.2f}", (k, val), xytext=(0, 9), textcoords="offset points",
                        ha="center", fontsize=8.5, color="#18614c", weight="bold")
        ax.set_xlim(0.35, 8.8)
        ax.set_ylim(-0.02, 0.92)
        ax.set_xticks(KS)
        ax.grid(axis="y", alpha=0.2)
        ax.spines[["top", "right"]].set_visible(False)
        if row == 0:
            km2 = {8: "0.74", 9: "0.11"}[res]
            ax.set_title(f"res {res}  (~{km2} km² cells)", fontsize=13, weight="bold")
        if row == 1:
            ax.set_xlabel("k — products that must agree", fontsize=11)
        if col == 0:
            ax.set_ylabel(mlab, fontsize=10.5)
fig.suptitle("Ranking the core region by k-of-6 agreement (green) against every single "
             "product (grey),\nthe geography null (red) and weighted fusion (blue)",
             fontsize=13)
fig.tight_layout(rect=(0, 0, 1, 0.96))
fig.savefig(os.path.join(FIGS, "rq3h_agreement_ranking.png"), dpi=150)
print("wrote figs/rq3h_agreement_ranking.png")
