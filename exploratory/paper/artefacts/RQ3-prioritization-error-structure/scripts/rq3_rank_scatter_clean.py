"""RQ3 clean rank scatter — product cell flag-count vs CEMS damage-count, with fit + rho.

Companion to the priority map: the statistical view of the same finding. Two panels
(MS, OSU) stacked to match the map. Per res-7 cell in Caraballeda: x = CEMS {2,3} damage
count, y = product flag count. Spearman rho + a linear trend line. Positive slope =
products rank neighbourhoods by damage.

Run: uv run --group etl --with scipy --with matplotlib python \
       exploratory/paper/artefacts/RQ3-prioritization-error-structure/scripts/rq3_rank_scatter_clean.py
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
from scipy.stats import spearmanr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
POS = (2, 3)
RES = 7
PRODUCTS = [("Microsoft", "ms_dmg", "#c62828"), ("OSU", "osu_dmg", "#2a78d6")]


def main():
    df = gp.building_flags(columns=["lon", "lat", "ms_dmg", "osu_dmg"])
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

    # single compact panel (Microsoft, the flagship) so it fits a slide column;
    # OSU is nearly identical (rho 0.81) and lives in the map + register.
    nm, col, c = PRODUCTS[0]
    prod = (inb[inb[col].to_numpy(dtype="float64", na_value=0.0) == 1]
            .groupby("cell").size().reindex(cells).fillna(0).to_numpy())
    rho, _ = spearmanr(truth, prod)
    rho_osu, _ = spearmanr(truth, (inb[inb["osu_dmg"].to_numpy(dtype="float64", na_value=0.0) == 1]
                                   .groupby("cell").size().reindex(cells).fillna(0).to_numpy()))
    fig, ax = plt.subplots(figsize=(6.2, 5.6))
    ax.scatter(truth, prod, s=70, color=c, alpha=0.65, edgecolor="white", lw=0.6, zorder=3)
    b1, b0 = np.polyfit(truth, prod, 1)
    xx = np.array([truth.min(), truth.max()])
    ax.plot(xx, b0 + b1 * xx, color=c, lw=2.5, zorder=2, alpha=0.85)
    ax.set_xlabel("real damage in the neighbourhood\n(CEMS damaged-or-destroyed points / cell)",
                  fontsize=12)
    ax.set_ylabel("Microsoft flags / cell", fontsize=12)
    ax.tick_params(labelsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(f"More real damage → more flags\n"
                 f"Microsoft ρ = {rho:.2f}   ·   OSU ρ = {rho_osu:.2f}   "
                 f"(each dot = one ~5 km² Caraballeda cell)", fontsize=12.5)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "rq3_rank_scatter_clean.png"), dpi=150)
    print(f"wrote rq3_rank_scatter_clean.png | MS rho {rho:.2f} | OSU rho {rho_osu:.2f}")


if __name__ == "__main__":
    main()
