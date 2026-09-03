"""RQ2r companion figure — precision lower -> upper bound ladder per product.

Draws the MEASURED convention (a flag earns credit only where the crowd actually
reviewed its location; unreviewed locations earn nothing) — the conservative reading.
@tbl-dial's crowd-adj column uses the extrapolated convention instead; both are in
rq2r_precision_bounds.csv and the manuscript captions state which is which.

Reads rq2r_precision_bounds.csv (no compute).

Run: uv run --with pandas --with matplotlib python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2r_bounds_fig.py
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
pb = pd.read_csv(os.path.join(HERE, "..", "rq2r_precision_bounds.csv"))

DEFS = [("P_floor", "expert points graded Damaged or Destroyed\n(the paper's reference: lower bound)", "#8a5a00", "o", True),
        ("P_grade", "also counting points graded Possibly damaged", "#c98a1e", "o", False),
        ("P_crowd", "also counting crowd-confirmed flags (MapSwipe)", "#2a78d6", "s", False),
        ("P_upper", "counting both additions  (upper bound)", "#1b4f8a", "D", True)]

o = pb.sort_values("P_upper").reset_index(drop=True)
fig, ax = plt.subplots(figsize=(11.5, 6.6))
for i, r in o.iterrows():
    ax.plot([r.P_floor, r.P_upper], [i, i], color="#c9d2d4", lw=3, zorder=1)
    for col, lbl, c, mk, filled in DEFS:
        ax.scatter(r[col], i, s=95, marker=mk, zorder=3, color=c if filled else "white",
                   edgecolor=c, linewidth=1.8, label=lbl if i == 0 else None)
    ax.text(-0.008, i, r["product"], ha="right", va="center", fontsize=13, weight="bold")
    ax.text(r.P_floor - 0.006, i, f"{r.P_floor:.3f}", ha="right", va="center",
            fontsize=9.5, color="#8a5a00")
    ax.text(r.P_grade, i + 0.30, f"{r.P_grade:.3f}", ha="center", va="bottom",
            fontsize=8.5, color="#c98a1e")
    ax.text(r.P_upper + 0.006, i, f"{r.P_upper:.3f}  ({r.P_upper/r.P_floor:.1f}×)",
            ha="left", va="center", fontsize=9.5, color="#1b4f8a", weight="bold")
    # coverage stays (it is what makes the upper bounds comparable across rows); the
    # per-row "understated" tag was removed 2026-09-03 — the footnote and the caption
    # already carry that mechanism once, calmly, for every row.
    ax.text(0.405, i, f"{r.crowd_cov_of_fps:.0%}", ha="left", va="center",
            fontsize=10, color="#5a6570")

ax.set_yticks([])
ax.set_xlim(0, 0.46)
ax.set_ylim(-0.8, len(o) + 0.6)
ax.text(0.405, len(o) - 0.25, "share of flags the\ncrowd reviewed", ha="left",
        va="bottom", fontsize=9.5, color="#5a6570", style="italic")
ax.set_xlabel("precision of the flags as shipped (core region, r = 10 m)", fontsize=11.5)
ax.legend(fontsize=9.5, loc="upper center", bbox_to_anchor=(0.5, -0.10), ncol=2,
          frameon=False, columnspacing=1.6, handletextpad=0.5)
ax.spines[["top", "right", "left"]].set_visible(False)
ax.set_title("The headline precision is a lower bound: crediting CEMS's own low-grade points and\n"
             "crowd-confirmed damage bounds each product's precision from above (2.2–3.6×)",
             fontsize=12.5)
fig.text(0.99, 0.012,
         "a flag earns credit only where the crowd actually reviewed its location and judged it damaged;\n"
         "locations the crowd never reviewed earn nothing, so low review coverage understates the upper bound",
         ha="right", fontsize=9, style="italic", color="#5a6570")
fig.tight_layout(rect=(0, 0.09, 1, 1))
fig.savefig(os.path.join(FIGS, "rq2r_bounds_ladder.png"), dpi=150)
print("wrote figs/rq2r_bounds_ladder.png")
