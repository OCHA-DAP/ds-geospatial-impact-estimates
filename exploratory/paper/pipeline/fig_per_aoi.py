"""Per-AOI scorecard heatmap (precision and recall per product x CEMS AOI), drawn from the
legacy-layout rq2i CSV that export_legacy.py writes from the pipeline rows. Replaces the drawing
half of the retired rq2i script, which re-scored everything to make this figure.

Usage: python fig_per_aoi.py  (from exploratory/paper) -> artefacts/RQ2-cems-footprint-points/figs/rq2i_per_aoi_scorecard.png
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "..", "artefacts", "RQ2-cems-footprint-points")
PRODUCTS = ["MS", "IMPACT", "OSU", "UH", "LIST", "UNEP"]


def main():
    out = pd.read_csv(os.path.join(A, "rq2i_per_aoi_scorecard.csv"))
    aois = (out[out.aoi != "ALL (as delivered)"].groupby("aoi").n_cems.max().sort_values(ascending=False)).index.tolist()
    aois = ["ALL (as delivered)"] + aois
    n_all = int(out[out.aoi == "ALL (as delivered)"].n_cems.max())
    share_cara = out[out.aoi == "Caraballeda"].n_cems.max() / n_all
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 6.5))
    for ax, colname, title in ((axes[0], "P_cems", "precision (CEMS floor, r = 10 m)"), (axes[1], "R_cems", "recall (CEMS, r = 10 m)")):
        M = np.full((len(PRODUCTS), len(aois)), np.nan)
        for i, p in enumerate(PRODUCTS):
            for j, a in enumerate(aois):
                r = out[(out["product"] == p) & (out.aoi == a)]
                if len(r) and r[colname].notna().any():
                    M[i, j] = float(r[colname].iloc[0])
        ax.imshow(M, cmap="YlOrRd", vmin=0, vmax=np.nanmax(M), aspect="auto")
        for i in range(len(PRODUCTS)):
            for j in range(len(aois)):
                r = out[(out["product"] == PRODUCTS[i]) & (out.aoi == aois[j])]
                if not len(r):
                    ax.text(j, i, "no\noverlap", ha="center", va="center", fontsize=8, color="#777")
                elif np.isnan(M[i, j]):
                    txt = "no ref\n(n=0)" if int(r.n_cems.iloc[0]) == 0 else "ref too\nthin"
                    ax.text(j, i, txt, ha="center", va="center", fontsize=8, color="#777")
                else:
                    dark = M[i, j] > 0.6 * np.nanmax(M)
                    ax.text(j, i, f"{M[i, j]:.2f}", ha="center", va="center", fontsize=10, color="white" if dark else "#1b1f24", weight="bold")
        ax.set_xticks(range(len(aois)), [f"{a}\n(n={int(out[out.aoi == a].n_cems.max())})" for a in aois], fontsize=10)
        ax.set_yticks(range(len(PRODUCTS)), PRODUCTS, fontsize=11)
        ax.set_title(title, fontsize=12)
    fig.suptitle("The scorecard is not one number per product: per-CEMS-AOI performance\n"
                 f"({share_cara:.0%} of reference damage points sit in Caraballeda; n = CEMS {{2,3}} points per AOI)", fontsize=12.5)
    fig.tight_layout()
    os.makedirs(os.path.join(A, "figs"), exist_ok=True)
    fig.savefig(os.path.join(A, "figs", "rq2i_per_aoi_scorecard.png"), dpi=150)
    print("wrote figs/rq2i_per_aoi_scorecard.png")


if __name__ == "__main__":
    main()
