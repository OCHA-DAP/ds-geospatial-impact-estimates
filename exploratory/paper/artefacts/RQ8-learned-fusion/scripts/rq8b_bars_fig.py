"""RQ8b deck bar chart — best-case vs as-delivered, against the day-zero baseline.

DEPRECATED (2026-08-06). No document references this figure, and it violates two conventions
the paper later adopted: it bars SINGLE-PRODUCT AP against a continuous score's AP (the
manuscript's Methods derive why that comparison is degenerate — AP_binary = P*R + (1-R)*pi),
and its reference line uses the RANDOM-FOREST null, the weaker learner in the common area,
where the logistic is primary. It is kept runnable against the r=20 CSVs it was built from
(renamed *_r20 on the same date) purely as history. Do not embed it in anything; the
operating-point comparison in rq8_best_f1_fig.py is the sanctioned replacement.

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

summ = pd.read_csv(os.path.join(HERE, "..", "rq8_summary_r20.csv")).set_index("model")["avg_precision"]
asdel = pd.read_csv(os.path.join(HERE, "..", "rq8b_asdelivered_baseline_r20.csv")).set_index("product")
baseline = float(summ["rf context-only (NO products)"])   # day-zero AP in the common area

prods = ["MS", "IMPACT", "OSU", "UH", "LIST", "UNEP"]
best = {p: float(summ[f"single: {p}"]) for p in prods}
deliv = {p: float(asdel.loc[p, "AP_product"]) for p in prods}
deliv_dz = {p: float(asdel.loc[p, "AP_dayzero"]) for p in prods}  # day-zero on FULL footprint
order = sorted(prods, key=lambda p: deliv[p])   # worst as-delivered at bottom

y = np.arange(len(order)) * 1.25
h = 0.34
fig, ax = plt.subplots(figsize=(13.5, 8.5))
ax.barh(y + h, [best[p] for p in order], height=h, color="#9db8d2",
        label="① product — best case (scored only in the common area ≈ Caraballeda)")
ax.barh(y, [deliv[p] for p in order], height=h, color="#1b4f8a",
        label="② product — as delivered (over its full shipped footprint)")
ax.barh(y - h, [deliv_dz[p] for p in order], height=h, color="#e08a7a",
        label="③ no-satellite baseline — on that same as-delivered footprint")
for yi, p in zip(y, order):
    ax.text(best[p] + 0.002, yi + h, f"{best[p]:.3f}", va="center", fontsize=10.5, color="#3a5a80")
    ax.text(deliv[p] + 0.002, yi, f"{deliv[p]:.3f}", va="center", fontsize=10.5,
            color="#1b4f8a", weight="bold")
    ax.text(deliv_dz[p] + 0.002, yi - h, f"{deliv_dz[p]:.3f}", va="center", fontsize=10.5,
            color="#b5533f")
    ax.text(-0.004, yi, p, va="center", ha="right", fontsize=14, weight="bold", color="#0b0b0b")

ax.axvline(baseline, color="#c62828", lw=2, ls="--", zorder=5)
ax.text(baseline, y.max() + 0.75, f"  baseline in the\n  common area ({baseline:.2f})",
        color="#c62828", fontsize=11, weight="bold", va="top")

ax.set_yticks([])
ax.set_xlim(0, max(max(best.values()), max(deliv_dz.values())) * 1.15)
ax.set_xlabel("average precision  (target: damaged OR destroyed buildings; higher = better)",
              fontsize=13)
ax.tick_params(axis="x", labelsize=12)
ax.legend(fontsize=11.5, loc="lower right", frameon=True)
ax.set_title("Products vs a no-satellite baseline, in two frames\n"
             "Best zone (①): products just tie the baseline.  As delivered (②): most fall "
             "below the baseline on their own footprint (③).", fontsize=13)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(os.path.join(FIGS, "rq8b_asdelivered_bars.png"), dpi=150)
print("wrote rq8b_asdelivered_bars.png")
for p in order:
    verdict = "BELOW" if deliv[p] < deliv_dz[p] else "above"
    print(f"  {p:6s} best {best[p]:.3f} | as-deliv {deliv[p]:.3f} vs its day-zero "
          f"{deliv_dz[p]:.3f}  [{verdict} baseline]")
