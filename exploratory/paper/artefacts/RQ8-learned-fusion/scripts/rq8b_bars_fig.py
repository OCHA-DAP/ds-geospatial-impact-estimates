"""RQ8b deck bar chart — best-case vs as-delivered, against the day-zero baseline.

Unified figure (user design, 2026-07-27): two bars per product —
  - best case: single-product AP in the COMMON area (core region ≈ Caraballeda), where
    every product and the day-zero baseline are scored on the same buildings;
  - as delivered: single-product AP over the product's FULL shipped footprint.
The day-zero (no-satellite) baseline is a single number in the common area (0.08), so it is
one vertical reference line, not a per-product bar.

Story: in the common area products merely TIE the free baseline; as delivered most fall
BELOW it (Microsoft holds — it only shipped the common area).

Sources: rq8_summary.csv (common-area single APs + context-only baseline),
rq8b_asdelivered_baseline.csv (as-delivered APs). No compute.

Run: uv run --with pandas --with matplotlib python \
       exploratory/paper/artefacts/RQ8-learned-fusion/scripts/rq8b_bars_fig.py
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")

summ = pd.read_csv(os.path.join(HERE, "..", "rq8_summary.csv")).set_index("model")["avg_precision"]
asdel = pd.read_csv(os.path.join(HERE, "..", "rq8b_asdelivered_baseline.csv")).set_index("product")
baseline = float(summ["rf context-only (NO products)"])   # day-zero AP in the common area

prods = ["MS", "IMPACT", "OSU", "UH", "LIST", "UNEP"]
best = {p: float(summ[f"single: {p}"]) for p in prods}
deliv = {p: float(asdel.loc[p, "AP_product"]) for p in prods}
order = sorted(prods, key=lambda p: deliv[p])   # worst as-delivered at bottom

y = np.arange(len(order))
h = 0.38
fig, ax = plt.subplots(figsize=(13, 7))
ax.barh(y + h/2, [best[p] for p in order], height=h, color="#9db8d2",
        label="best case — scored only in the common area (≈ Caraballeda)")
ax.barh(y - h/2, [deliv[p] for p in order], height=h, color="#1b4f8a",
        label="as delivered — scored over everything the product shipped")
for yi, p in zip(y, order):
    ax.text(best[p] + 0.002, yi + h/2, f"{best[p]:.3f}", va="center", fontsize=11, color="#3a5a80")
    ax.text(deliv[p] + 0.002, yi - h/2, f"{deliv[p]:.3f}", va="center", fontsize=11,
            color="#1b4f8a", weight="bold")
    ax.text(-0.004, yi, p, va="center", ha="right", fontsize=14, weight="bold", color="#0b0b0b")

ax.axvline(baseline, color="#e34948", lw=2.4, ls="--", zorder=5)
ax.text(baseline, len(order) - 0.35, f"  no-satellite\n  day-zero baseline ({baseline:.2f})",
        color="#c62828", fontsize=12, weight="bold", va="top")

ax.set_yticks([])
ax.set_xlim(0, max(max(best.values()), max(deliv.values())) * 1.15)
ax.set_xlabel("average precision  (target: damaged OR destroyed buildings; higher = better)",
              fontsize=13)
ax.tick_params(axis="x", labelsize=12)
ax.legend(fontsize=12, loc="lower right", frameon=True)
ax.set_title("Same products, two frames — vs a model that uses no satellite data\n"
             "Best zone: products merely tie the baseline.  As delivered: most fall below it.",
             fontsize=13.5)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(os.path.join(FIGS, "rq8b_asdelivered_bars.png"), dpi=150)
print("wrote rq8b_asdelivered_bars.png")
print(f"baseline (common area) = {baseline}")
for p in order:
    print(f"  {p:6s} best {best[p]:.3f} | as-delivered {deliv[p]:.3f}")
