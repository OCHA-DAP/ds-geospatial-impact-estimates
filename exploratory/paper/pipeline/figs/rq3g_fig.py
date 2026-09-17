"""Area ranking by damage count vs damage fraction, per product and resolution (the brief's
@fig-fracrank), drawn from the signed-off frozen/rq3g_frac_vs_count.csv. Split out of the archived
rq3g_frac_ranking.py so the figure no longer requires re-running the analysis.

Usage: python pipeline/figs/rq3g_fig.py  (from exploratory/paper) -> figures/rq3g_frac_vs_count_rho.png
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.join(HERE, "..", "..")
RESOS = (8, 7)


def main():
    out = pd.read_csv(os.path.join(PAPER, "frozen", "rq3g_frac_vs_count.csv"))
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), sharey=True)
    for ax, res in zip(axes, RESOS):
        v = out[out.res == res].reset_index(drop=True)
        yp = np.arange(len(v))
        ax.scatter(v.rho_count, yp, s=90, color="#1b4f8a", zorder=3, label="ranked by COUNT")
        ax.scatter(v.rho_frac, yp, s=90, color="#c98a1e", zorder=3, marker="s", label="ranked by FRACTION (cells ≥20 bldgs)")
        ax.scatter(v.rho_null_count, yp, s=60, facecolor="white", edgecolor="#1b4f8a", zorder=3, label="geography null (count)")
        ax.scatter(v.rho_null_frac, yp, s=60, facecolor="white", edgecolor="#c98a1e", marker="s", zorder=3, label="geography null (fraction)")
        for i, r in v.iterrows():
            ax.plot([r.rho_frac, r.rho_count], [i, i], color="#c9d2d4", lw=2, zorder=1)
        ax.set_yticks(yp, v["product"], fontsize=11)
        ax.axvline(0, color="#999", lw=0.8)
        ax.set_title(f"res {res} (~{ {8: '0.74', 7: '5.2'}[res] } km² cells)", fontsize=12)
        ax.set_xlabel("Spearman ρ vs CEMS", fontsize=11)
        ax.grid(axis="x", alpha=0.25)
    axes[0].legend(fontsize=9, loc="lower left", frameon=False)
    fig.suptitle("Area ranking by damage COUNT vs damage FRACTION (as-delivered scope)", fontsize=13)
    fig.tight_layout()
    os.makedirs(os.path.join(PAPER, "figures"), exist_ok=True)
    fig.savefig(os.path.join(PAPER, "figures", "rq3g_frac_vs_count_rho.png"), dpi=150)
    print("wrote figures/rq3g_frac_vs_count_rho.png")


if __name__ == "__main__":
    main()
