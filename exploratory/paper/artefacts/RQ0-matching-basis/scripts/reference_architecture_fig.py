"""Reference-architecture schematic — the three validation datasets, side by side.

Pure diagram (no data). Kills the recurring MapSwipe-vs-ChatMap confusion: shows who each
reference is, its geometry (point vs hex-cell — the crux), which error type it can measure,
its blind spot, and which metric it drives. Goes in the deck and both paper docs.

Run: uv run --with matplotlib python \
       exploratory/paper/artefacts/RQ0-matching-basis/scripts/reference_architecture_fig.py
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
os.makedirs(FIGS, exist_ok=True)

BLUE, ORANGE, GREEN, INK = "#2a6fb0", "#d98014", "#2e8b57", "#1b1f24"
cards = [
    dict(x=0.03, c=BLUE, name="Copernicus EMS (CEMS)",
         who="expert analysts read VHR imagery",
         geom="building-level POINTS",
         measures="false alarms  AND  misses",
         blind="only inside its mapped extents\n(96% in one AOI, Caraballeda)",
         drives="the core scorecard:\nprecision floor + recall",
         note="the primary reference"),
    dict(x=0.36, c=ORANGE, name="MapSwipe  (volunteers)",
         who="400+ people vote on AI-flagged spots",
         geom="~50 m HEX-CELL votes  (not points)",
         measures="false alarms ONLY\n(never saw un-flagged places)",
         blind="cannot find a single miss;\nverdict is per 50 m cell, not per building",
         drives="adjudicates flags CEMS missed\n→ precision 0.08 → ~0.24\n(coarse, cell-level: upper estimate)",
         note="the crowd"),
    dict(x=0.69, c=GREEN, name="ChatMap  (field teams)",
         who="damage reported from the ground",
         geom="field POINTS  (~building level)",
         measures="misses ONLY\n(positives, no survey frame)",
         blind="cannot judge a false alarm;\nsparse (415 pts)",
         drives="recall by damage grade;\nunions with CEMS points\n→ precision +5–9%",
         note="the ground truth that reaches inland"),
]

fig, ax = plt.subplots(figsize=(15, 8.4))
ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
ax.text(0.5, 0.965, "Three reference datasets — who they are, and what each can measure",
        ha="center", fontsize=19, weight="bold", color=INK)
ax.text(0.5, 0.918, "They are used SEPARATELY, each only for the error type it can see — "
        "because their blind spots don't overlap.",
        ha="center", fontsize=12.5, color="#52514e", style="italic")

W, top, bot = 0.28, 0.86, 0.20
rows = [("who", "who"), ("geometry", "geom"), ("measures", "measures"),
        ("blind spot", "blind"), ("drives", "drives")]
for cd in cards:
    x = cd["x"]
    ax.add_patch(FancyBboxPatch((x, bot), W, top - bot, boxstyle="round,pad=0.008",
                                linewidth=2.2, edgecolor=cd["c"], facecolor="#ffffff",
                                mutation_aspect=1.1, zorder=2))
    ax.add_patch(FancyBboxPatch((x, top - 0.085), W, 0.085, boxstyle="round,pad=0.008",
                                linewidth=0, facecolor=cd["c"], mutation_aspect=1.1, zorder=3))
    ax.text(x + W/2, top - 0.03, cd["name"], ha="center", va="center", fontsize=14.5,
            weight="bold", color="white", zorder=4)
    ax.text(x + W/2, top - 0.065, cd["note"], ha="center", va="center", fontsize=10.5,
            color="white", style="italic", zorder=4)
    yy = top - 0.135
    for label, key in rows:
        ax.text(x + 0.015, yy, label.upper(), fontsize=8.5, weight="bold",
                color=cd["c"], va="top")
        ax.text(x + 0.015, yy - 0.028, cd[key], fontsize=10.3, color=INK, va="top")
        gap = 0.028 + 0.026 * (cd[key].count("\n") + 1)
        yy -= gap + 0.014

# bottom summary bar: precision <-> recall
ay = 0.115
ax.annotate("", xy=(0.82, ay), xytext=(0.18, ay),
            arrowprops=dict(arrowstyle="<->", lw=2, color="#bbb"))
ax.text(0.16, ay, "PRECISION", ha="right", va="center", fontsize=13, weight="bold", color=INK)
ax.text(0.16, ay - 0.045, "are the flags real?", ha="right", va="center", fontsize=10.5,
        color="#52514e")
ax.text(0.84, ay, "RECALL", ha="left", va="center", fontsize=13, weight="bold", color=INK)
ax.text(0.84, ay - 0.045, "did we catch the damage?", ha="left", va="center", fontsize=10.5,
        color="#52514e")
ax.text(0.5, ay + 0.055,
        r"$\bf{CEMS}$ anchors both  ·  $\bf{MapSwipe}$ sharpens precision  ·  "
        r"$\bf{ChatMap}$ extends recall", ha="center", fontsize=12, color="#333")

fig.savefig(os.path.join(FIGS, "reference_architecture.png"), dpi=150, bbox_inches="tight")
print("wrote reference_architecture.png")
