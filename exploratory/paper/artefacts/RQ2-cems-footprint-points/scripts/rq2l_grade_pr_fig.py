"""RQ2l companion figure — destruction bias in BOTH precision and recall (CEMS grades).

Two panels, one reference (CEMS's own grades: Damaged=class2, Destroyed=class3), one frame
(core region, r=10 m). Left: recall of each grade. Right: precision against each grade.
Both slope toward Destroyed for the appearance/debris products (MS/UH/UNEP) and stay flat
for the coherence products (OSU/IMPACT) — the destruction bias shows in both metrics.

Reads rq2l_cems_grade_recall.csv (no compute).

Run: uv run --with pandas --with matplotlib python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2l_grade_pr_fig.py
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
df = pd.read_csv(os.path.join(HERE, "..", "rq2l_cems_grade_recall.csv")).set_index("product")

COL = {"MS": "#c62828", "UH": "#e08214", "UNEP": "#8a5a00",   # appearance/debris (biased)
       "OSU": "#2a78d6", "IMPACT": "#4a90d9", "LIST": "#7fb069"}  # coherence-ish (flat)

fig, (axR, axP) = plt.subplots(1, 2, figsize=(13.5, 6.5))

for ax, (lo, hi, ylab, title) in ((axR, ("R_of_damaged", "R_of_destroyed",
        "recall — share of graded buildings found", "RECALL by grade")),
        (axP, ("P_vs_damaged", "P_vs_destroyed",
        "precision — share of flags near graded damage", "PRECISION by grade"))):
    dy = {"UH": 10, "UNEP": -10}  # UH and UNEP coincide at Destroyed — nudge labels apart
    for p in df.index:
        ax.plot([0, 1], [df.loc[p, lo], df.loc[p, hi]], marker="o", ms=8, lw=2.4,
                color=COL[p])
        ax.annotate(p, (1, df.loc[p, hi]), textcoords="offset points",
                    xytext=(8, dy.get(p, 0)), fontsize=11, color=COL[p], weight="bold",
                    va="center")
    ax.set_xlim(-0.15, 1.4)
    ax.set_xticks([0, 1], ["Damaged\n(class 2)", "Destroyed\n(class 3)"], fontsize=12)
    ax.set_ylabel(ylab, fontsize=11.5)
    ax.set_title(title, fontsize=14, weight="bold")
    ax.set_ylim(0)
    ax.tick_params(axis="y", labelsize=10)

fig.suptitle("Every product detects DESTRUCTION better than DAMAGE — in both metrics\n"
             "steep = destruction-biased (MS/UH/UNEP);  flat = grade-neutral (OSU/IMPACT/LIST)",
             fontsize=13.5)
fig.tight_layout()
fig.savefig(os.path.join(FIGS, "rq2l_grade_pr.png"), dpi=150)
print("wrote rq2l_grade_pr.png")
