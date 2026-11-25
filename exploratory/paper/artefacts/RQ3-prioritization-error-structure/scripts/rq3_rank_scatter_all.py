"""RQ3 rank scatter — all six products on one plot, in rank space.

Products flag at wildly different rates, so raw counts aren't comparable on one axis.
Spearman rho IS a rank correlation, so we plot in rank space: x = each cell's rank by
CEMS damage (0 = least, 1 = most), y = its rank by the product's flags. Points near the
diagonal = the product ranks that cell correctly. One colour per product, per-product
trend line, rho in the legend. res-7 cells, Caraballeda.

Run: uv run --group etl --with scipy --with matplotlib python \
       exploratory/paper/artefacts/RQ3-prioritization-error-structure/scripts/rq3_rank_scatter_all.py
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
from scipy.stats import spearmanr, rankdata
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
POS = (2, 3)
RES = 7
MEMBERS = [("Microsoft", "ms_dmg", "#c62828"), ("IMPACT", "sar_dmg", "#4a90d9"),
           ("OSU", "osu_dmg", "#2a78d6"), ("UH", "uh_dmg", "#e08214"),
           ("LIST", "list_dmg", "#2e8b57"), ("UNEP", "debris_dmg", "#8a5a00")]


def fracrank(a):
    return (rankdata(a) - 1) / (len(a) - 1)


def main():
    cols = [m[1] for m in MEMBERS]
    df = gp.building_flags(columns=["lon", "lat", *cols])
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326)
    ext = gp.cems_extent().query("is_latest")
    car = ext[ext.aoi_name == "Caraballeda"].to_crs(4326).geometry.make_valid().union_all()
    inb = bld[bld.geometry.within(car)].copy()
    inb["cell"] = [h3.latlng_to_cell(p.y, p.x, RES) for p in inb.geometry]
    cems = gp.cems_points()
    cems = cems[cems.damage_class.isin(POS)].to_crs(4326)
    cems = cems[cems.geometry.within(car)].copy()
    cems["cell"] = [h3.latlng_to_cell(p.y, p.x, RES) for p in cems.geometry]
    cems_ct = cems.groupby("cell").size()

    cells = sorted(set(inb.cell) | set(cems_ct.index))
    truth = cems_ct.reindex(cells).fillna(0).to_numpy()
    tx = fracrank(truth)
    rng = np.random.default_rng(884)

    fig, ax = plt.subplots(figsize=(7.2, 6.6))
    ax.plot([0, 1], [0, 1], color="#bbb", lw=1.5, ls="--", zorder=1)
    for nm, col, c in MEMBERS:
        prod = (inb[inb[col].to_numpy(dtype="float64", na_value=0.0) == 1]
                .groupby("cell").size().reindex(cells).fillna(0).to_numpy())
        rho, _ = spearmanr(truth, prod)
        py = fracrank(prod)
        jx = tx + rng.uniform(-0.028, 0.028, len(tx))  # de-stripe tied ranks
        jy = py + rng.uniform(-0.020, 0.020, len(py))
        ax.scatter(jx, jy, s=24, color=c, alpha=0.35, edgecolor="none", zorder=3)
        b1, b0 = np.polyfit(tx, py, 1)
        ax.plot([0, 1], [b0, b0 + b1], color=c, lw=2.6, zorder=4,
                label=f"{nm}   ρ = {rho:.2f}")
    ax.set_xlabel("neighbourhood rank by REAL damage  (0 = least, 1 = most)", fontsize=12)
    ax.set_ylabel("neighbourhood rank by the product's flags", fontsize=12)
    ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)
    ax.tick_params(labelsize=11)
    ax.legend(fontsize=11, loc="upper left", framealpha=0.9)
    ax.set_title("Do products rank neighbourhoods by real damage?\n"
                 "dashed = perfect ranking · closer to it = better  "
                 "(res-7 cells, Caraballeda)", fontsize=12.5)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "rq3_rank_scatter_all.png"), dpi=150)
    print("wrote rq3_rank_scatter_all.png")


if __name__ == "__main__":
    main()
