"""Schematic: how the day-zero baseline (and, by extension, the weighted fusion) is built.

Pure diagram — no data. Three context inputs known within hours → one spatially-blocked
model (logistic and random forest are both fitted; the stronger in each frame is the one
reported) → a CONTINUOUS risk score → (sweep threshold) → a family of flag lists
= a PR curve, against which a single product is one already-thresholded point. Adding the
six product flags to the same model = the weighted fusion.

Run: uv run --with matplotlib --with numpy python \
       exploratory/paper/artefacts/RQ8-learned-fusion/scripts/rq8_dayzero_schematic.py
"""
from __future__ import annotations
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

FIGS = os.path.join(os.path.dirname(__file__), "..", "figs")
os.makedirs(FIGS, exist_ok=True)

BLUE, GREY, RED, INK = "#3b7dc4", "#5a6570", "#e34948", "#12202e"


def box(ax, x, y, w, h, text, fc, ec, fs=12, weight="normal", tc=INK):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
                                linewidth=1.6, edgecolor=ec, facecolor=fc, zorder=2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            weight=weight, color=tc, zorder=3)


def arrow(ax, x0, y0, x1, y1, color=INK, lw=2.0, ls="-"):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=18,
                                 lw=lw, color=color, linestyle=ls, zorder=1,
                                 shrinkA=2, shrinkB=2))


fig, ax = plt.subplots(figsize=(13.5, 5.4))
ax.set_xlim(0, 13.5); ax.set_ylim(0, 5.4); ax.axis("off")

# --- three inputs (left) --------------------------------------------------------
inputs = ["coast distance (m)", "building density", "ShakeMap intensity (MMI)"]
iy = [3.75, 2.55, 1.35]
for t, y in zip(inputs, iy):
    box(ax, 0.3, y, 3.0, 0.9, t, "#e8f1fa", BLUE, fs=12.5)
ax.text(1.8, 4.95, "known within HOURS —\nno satellite input", ha="center", va="center",
        fontsize=11, style="italic", color=BLUE, weight="bold")

# --- model box (center) ---------------------------------------------------------
# Both learners are fitted and the stronger in each frame is reported (logistic wins the core
# region, the forest wins the larger as-delivered footprints) — a null is only meaningful if it
# is the best honest account of "just geography". Naming only one learner here previously
# contradicted @fig-bestf1, which labels the logistic as primary.
mx, my, mw, mh = 4.35, 1.91, 3.15, 1.78
box(ax, mx, my, mw, mh, "logistic  ·  random forest\n(whichever scores higher)\n"
    "spatially-blocked 5 km² CV\ntarget: CEMS damage {2,3}",
    "#f1f0ea", INK, fs=10.5, weight="bold")
for y in iy:
    arrow(ax, 3.32, y + 0.45, mx - 0.14, my + mh / 2)

# NOTE: the weighted fusion is deliberately NOT drawn here — this figure is only about how
# the day-zero baseline is constructed, and adding the fusion box invited the question "why
# is fusion in a day-zero diagram?". The relationship (fusion = this model + the six product
# flags) is stated in the Methods text instead.
ax.text(5.925, 1.62, "no satellite product enters this model",
        ha="center", va="center", fontsize=11, style="italic", color=GREY)
# The honest caveat the box diagram would otherwise hide: fitting needs the labels.
ax.text(5.925, 1.12, "…but fitting it needs the damage labels themselves,\n"
        "so it is a RETROSPECTIVE null — not runnable on day zero",
        ha="center", va="center", fontsize=11, weight="bold", color=RED)

# --- continuous score (right of model) ------------------------------------------
sx, sy, sw, sh = 8.05, 2.05, 2.05, 1.5
box(ax, sx, sy, sw, sh, "continuous\nper-building\nrisk  ∈ [0, 1]", "#fdeceb", RED,
    fs=12.5, weight="bold", tc=RED)
arrow(ax, mx + mw + 0.02, my + mh / 2, sx - 0.02, sy + sh / 2)

# --- PR-curve inset (far right): sweeping the threshold = a family of flag lists --
ins = fig.add_axes([0.795, 0.12, 0.185, 0.72])
r = np.linspace(0.02, 1, 200)
p = 0.06 + 0.32 * np.exp(-2.6 * r)           # illustrative day-zero-like PR curve
ins.plot(r, p, color=RED, lw=2.4, ls="--")
ins.scatter([0.46], [0.14], s=70, color=GREY, zorder=5)
ins.annotate("one product\n= one point", (0.46, 0.14), xytext=(0.52, 0.28),
             fontsize=9.5, color=GREY,
             arrowprops=dict(arrowstyle="-", color=GREY, lw=0.8))
ins.set_xlim(0, 1); ins.set_ylim(0, 0.42)
ins.set_xlabel("recall", fontsize=10); ins.set_ylabel("precision", fontsize=10)
ins.tick_params(labelsize=8)
ins.set_title("every threshold =\na flag list", fontsize=10.5, color=RED)
arrow(ax, sx + sw + 0.02, sy + sh / 2, 10.55, sy + sh / 2, color=RED)

ax.text(6.75, 5.05, "Building the geography null model", ha="center", fontsize=16,
        weight="bold", color=INK)
fig.savefig(os.path.join(FIGS, "rq8_dayzero_schematic.png"), dpi=150,
            bbox_inches="tight")
print("wrote figs/rq8_dayzero_schematic.png")
