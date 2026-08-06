"""RQ2e grade-slope figure — recall falls with damage grade for every dataset.

Visualizes tbl-field (rq2_chatmap_recall.csv): field-frame recall (r=20 m vs ChatMap)
at "complete" vs "significant" grade, one sloping line per dataset. This is the
recall-side counterpart of the precision floor: CEMS-frame recall over-represents
destruction (the easy class), so measured recall is a ceiling; the field frame shows
how far recall falls when lighter damage is in the denominator. Minimal grade omitted
(n <= 24, indicative only).

Run: uv run --with pandas --with matplotlib python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2e_grade_slope_fig.py
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
os.makedirs(FIGS, exist_ok=True)

df = pd.read_csv(os.path.join(HERE, "..", "rq2_chatmap_recall.csv"))
ROWS = {"CEMS {2,3}": ("CEMS (expert reference)", "#1b1f24", 2.6),
        "≥1-of-6 votes (core region)": ("union of six products", "#2a78d6", 2.6),
        "OSU": ("OSU", "#9aa5b1", 1.6), "LIST": ("LIST", "#9aa5b1", 1.6),
        "MS": ("Microsoft", "#9aa5b1", 1.6), "IMPACT v2": ("IMPACT v2", "#9aa5b1", 1.6),
        "UH": ("UH", "#9aa5b1", 1.6),
        "UNEP debris (core region)": ("UNEP", "#9aa5b1", 1.6)}

LABEL_DY = {"OSU": 6, "LIST": -9, "UNEP": 5, "UH": -12}
fig, ax = plt.subplots(figsize=(9, 7.5))
for key, (label, color, lw) in ROWS.items():
    r = df[df.reference == key]
    if not len(r):
        continue
    c, s = float(r.complete_r20.iloc[0]), float(r.significant_r20.iloc[0])
    ax.plot([0, 1], [c, s], c=color, lw=lw, marker="o", ms=7,
            zorder=4 if lw > 2 else 2)
    ax.annotate(f"{label}  ({c:.2f} → {s:.2f})", (1, s), textcoords="offset points",
                xytext=(10, LABEL_DY.get(label, -3)), fontsize=10.5, color=color)

ax.set_xlim(-0.15, 1.9)
ax.set_ylim(0, 1.02)
ax.set_xticks([0, 1], ['field-assessed\n"complete" destruction',
                       'field-assessed\n"significant" damage'], fontsize=12)
ax.set_ylabel("recall vs ChatMap field reports (field frame, r = 20 m)", fontsize=12)
ax.tick_params(axis="y", labelsize=11)
ax.set_title("Recall falls with damage grade — for the products AND the expert "
             "reference.\nCEMS-frame recall inherits this skew: it is a ceiling, "
             "not a floor.", fontsize=12.5)
fig.tight_layout()
fig.savefig(os.path.join(FIGS, "rq2e_grade_slope.png"), dpi=150)
print("wrote figs/rq2e_grade_slope.png")
