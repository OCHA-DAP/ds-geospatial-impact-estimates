"""Figure for RQ3f — does the geography null rank areas as well as the products?

Single panel at the ~5 km² sector scale (the scale triage actually happens at), all six
evaluated products. The ~0.7 km² results are in rq3f_null_ranking.csv and point the same
way; showing both resolutions on a slide introduced a distinction the audience does not need.

Reads rq3f_null_ranking.csv — no refitting.
Colours are HDX v2 tokens (ds-knowledge-base-internal/style-reference/tokens.md).

Run: uv run --with pandas --with matplotlib --with numpy python \
       exploratory/paper/artefacts/RQ3-prioritization-error-structure/scripts/rq3f_null_ranking_fig.py
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
os.makedirs(FIGS, exist_ok=True)

PROD, NULL = "#3f4748", "#c44536"      # --hdx-neutral-8, --hdx-error-5
RES = 7                                 # ~5 km2 sectors — the triage scale

d = pd.read_csv(os.path.join(HERE, "..", "rq3f_null_ranking.csv"))
s = d[d.res == RES].sort_values("rho_product", ascending=False).reset_index(drop=True)
n_null_wins = int((s.rho_null > s.rho_product).sum())

fig, ax = plt.subplots(figsize=(12.5, 6.4))
y = np.arange(len(s)); h = 0.37
ax.barh(y - h / 2, s.rho_product, height=h, color=PROD, zorder=3, label="satellite product")
ax.barh(y + h / 2, s.rho_null, height=h, color=NULL, zorder=3,
        label="geography null (coast distance + building density + shaking)")

for i, r in s.iterrows():
    ax.text(max(r.rho_product, 0) + 0.012, i - h / 2, f"{r.rho_product:.2f}",
            va="center", fontsize=12.5, color=PROD, weight="bold")
    ax.text(r.rho_null + 0.012, i + h / 2, f"{r.rho_null:.2f}",
            va="center", fontsize=12.5, color=NULL, weight="bold")
    ax.text(0.985, i, "product wins" if r.rho_product > r.rho_null else "null wins",
            transform=ax.get_yaxis_transform(), ha="right", va="center",
            fontsize=11, style="italic",
            color=PROD if r.rho_product > r.rho_null else NULL, zorder=5)

ax.axvline(0, color="#5e6a6b", lw=1, zorder=4)
ax.set_yticks(y, s["product"], fontsize=14)
ax.set_xlim(-0.18, 0.95)
ax.invert_yaxis()
ax.grid(axis="x", alpha=0.25, zorder=0)
ax.spines[["top", "right", "left"]].set_visible(False)
ax.tick_params(labelsize=11.5)
ax.set_xlabel("Spearman rank correlation with the expert damage count per ~5 km² sector  "
              "(higher = ranks the worst-hit areas better)", fontsize=12.5)
ax.set_title(f"Ranking which areas were worst hit:\n"
             f"coarse geography beats {n_null_wins} of the {len(s)} products",
             fontsize=15.5, weight="bold", color="#1f2324")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2, fontsize=11.5,
          frameon=False)
fig.tight_layout(rect=(0, 0.04, 1, 1))
out = os.path.join(FIGS, "rq3f_null_ranking.png")
fig.savefig(out, dpi=150)
print(f"wrote {os.path.relpath(out, HERE)}")
print(s[["product", "rho_product", "rho_null", "delta"]].to_string(index=False))
