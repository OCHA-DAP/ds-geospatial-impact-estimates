"""RQ8c companion figures — reference-basis sensitivity slope charts.

Two figures from rq8c_basis_pr_r10.csv (no compute):
  * rq8c_basis_precision_r10.png — precision only (the manuscript's appendix figure)
  * rq8c_basis_prf1_r10.png     — P / R / F1 three-panel (registry / findings)

Style follows the fig-bestf1 family: grey product band, fusion #18614c, voting #51ac92,
nulls #c44536 / #dc8f86; every series direct-labelled (identity never colour-alone).

Run: uv run --with pandas --with matplotlib python \
       exploratory/paper/artefacts/RQ8-learned-fusion/scripts/rq8c_basis_fig.py
"""
from __future__ import annotations
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
os.makedirs(FIGS, exist_ok=True)
gb = pd.read_csv(os.path.join(HERE, "..", "rq8c_basis_pr_r10.csv"))

PRODUCTS = ["MS", "IMPACT", "OSU", "UH", "LIST", "UNEP"]
CONS = {"weighted fusion": "#18614c", "flat k-of-6 voting": "#51ac92",
        "geography null (logistic)": "#c44536", "geography null (rand. forest)": "#dc8f86"}
BASES = ["destroyed", "dmg+destroyed", "incl_possibly"]
XLBL = ["Destroyed only\n{3}", "Damaged or Destroyed\n{2,3}  (the paper)",
        "incl. Possibly damaged\n{1,2,3}"]
XLBL_SHORT = ["{3}\ndestroyed", "{2,3}\npaper", "{1,2,3}\n+ possibly"]


def slope_panel(ax, metric, label_right=True, lbl_fs=9.5, short_x=False):
    w = gb.pivot(index="predictor", columns="basis", values=metric)[BASES]
    pv = w.loc[PRODUCTS]
    ax.fill_between([0, 1, 2], pv.min(), pv.max(), color="#9db1b3", alpha=0.22, zorder=1)
    for p in PRODUCTS:
        ax.plot([0, 1, 2], w.loc[p], color="#9db1b3", lw=1.4, marker="o", ms=4, zorder=2)
    for nm, c in CONS.items():
        ax.plot([0, 1, 2], w.loc[nm], color=c, lw=2.6, marker="o", ms=7, zorder=3)
    ax.axvline(1, color="#5a6570", lw=0.8, ls=(0, (4, 3)), alpha=0.55, zorder=0)
    ax.set_xlim(-0.15, 2.15 if not label_right else 3.35)
    ax.set_xticks([0, 1, 2], XLBL_SHORT if short_x else XLBL, fontsize=9.5)
    ax.tick_params(axis="y", labelsize=9.5)
    ax.spines[["top", "right"]].set_visible(False)
    if label_right:  # dodge right-end labels vertically
        ends = sorted([(w.loc[p, BASES[-1]], p, "#5a6570", 8.5) for p in PRODUCTS]
                      + [(w.loc[n, BASES[-1]], n, CONS[n], lbl_fs) for n in CONS],
                      key=lambda t: t[0])
        span = ax.get_ylim()[1] - ax.get_ylim()[0]
        min_gap = 0.042 * max(span, w.to_numpy().max())
        ys = []
        for v, *_ in ends:
            yy = v
            if ys and yy - ys[-1] < min_gap:
                yy = ys[-1] + min_gap
            ys.append(yy)
        for yy, (v, nm, c, fs) in zip(ys, ends):
            short = {"geography null (logistic)": "geo null (logistic)",
                     "geography null (rand. forest)": "geo null (forest)"}.get(nm, nm)
            ax.annotate(f"{short}  {v:.3f}", (2, v), xytext=(2.12, yy),
                        textcoords="data", fontsize=fs, color=c,
                        weight="bold" if nm in CONS else "normal", va="center",
                        arrowprops=dict(arrowstyle="-", color=c, lw=0.6, alpha=0.5))


# ---- precision only (appendix figure) ----
fig, ax = plt.subplots(figsize=(10.5, 7))
slope_panel(ax, "precision")
ax.set_ylabel("precision — share of flags within 10 m of a reference point", fontsize=11)
ax.set_title("Precision is a function of which CEMS grades count as damage —\n"
             "levels roughly double per step (mechanical: more reference, same flags); "
             "no comparison flips",
             fontsize=12.5)
fig.tight_layout()
fig.savefig(os.path.join(FIGS, "rq8c_basis_precision_r10.png"), dpi=150)
print("wrote figs/rq8c_basis_precision_r10.png")

# ---- P / R / F1 three-panel (registry) ----
fig, axes = plt.subplots(1, 3, figsize=(16.5, 6.4))
for ax, (m, t) in zip(axes, [("precision", "PRECISION"), ("recall", "RECALL"), ("f1", "F1")]):
    slope_panel(ax, m, label_right=(m == "f1"), lbl_fs=9, short_x=True)
    ax.set_title(t, fontsize=13, weight="bold")
    ax.set_ylim(0)
handles = [Line2D([], [], color=c, lw=2.6, marker="o", ms=6, label=n) for n, c in CONS.items()]
handles.append(Line2D([], [], color="#9db1b3", lw=1.4, marker="o", ms=4,
                      label="single products (band)"))
fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.945), ncol=5,
           fontsize=9.5, frameon=False)
fig.suptitle("Every metric, re-scored under three definitions of the CEMS reference "
             "(same flags, same operating points — only the target changes)", fontsize=13)
fig.tight_layout(rect=(0, 0, 1, 0.90))
fig.savefig(os.path.join(FIGS, "rq8c_basis_prf1_r10.png"), dpi=150)
print("wrote figs/rq8c_basis_prf1_r10.png")
