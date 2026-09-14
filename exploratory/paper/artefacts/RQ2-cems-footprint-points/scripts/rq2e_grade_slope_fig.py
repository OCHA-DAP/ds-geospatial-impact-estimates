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

fig, ax = plt.subplots(figsize=(9, 7.5))
labels = []
for key, (label, color, lw) in ROWS.items():
    r = df[df.reference == key]
    if not len(r):
        continue
    c, s = float(r.complete_r20.iloc[0]), float(r.significant_r20.iloc[0])
    ax.plot([0, 1], [c, s], c=color, lw=lw, marker="o", ms=7,
            zorder=4 if lw > 2 else 2)
    labels.append((s, f"{label}  ({c:.2f} → {s:.2f})", color))
# stack the right-hand labels so none overprint: sort by value, then push apart to a
# minimum gap in data units (labels keep their line's value in the text itself)
MIN_GAP = 0.032
labels.sort(key=lambda x: x[0])
ys = [s for s, _, _ in labels]
for i in range(1, len(ys)):
    ys[i] = max(ys[i], ys[i - 1] + MIN_GAP)
for i in range(len(ys) - 2, -1, -1):  # pull back down where the stack overshoots the axis top
    ys[i] = min(ys[i], ys[i + 1] - MIN_GAP)
for (s, txt, color), y in zip(labels, ys):
    ax.annotate(txt, (1, s), xytext=(1.06, y), textcoords="data", fontsize=10.5, color=color,
                va="center", arrowprops=dict(arrowstyle="-", color=color, lw=0.6, alpha=0.6)
                if abs(y - s) > 0.012 else None)

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
