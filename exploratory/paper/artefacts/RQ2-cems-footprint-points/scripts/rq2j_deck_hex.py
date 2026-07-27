"""RQ2j deck hex map — Microsoft, two decision-relevant metrics, slide-legible.

The register has 4-panel maps for all six products; for the deck we want one clean,
wide, legible figure. Microsoft (best story: the west/east split is geographic). Two
stacked full-width panels: precision (are the flags real here?) and field-visits-per-
verified-find (operational cost here). res-7 cells, CODAB basemap, grey where thin.

Run: uv run --group etl --with scipy --with matplotlib python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2j_deck_hex.py
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
from scipy.spatial import cKDTree
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
POS = (2, 3)
RES = 7
MIN_FLAGS, MIN_CEMS = 20, 10


def hexpoly(c):
    return MplPolygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)], closed=True)


def main():
    df = gp.building_flags(columns=["lon", "lat", "ms_dmg"])  # OSU pin irrelevant here
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                           crs=4326).to_crs(gp.METRIC_CRS)
    reg = (gp.to_metric(gp.cems_extent().query("is_latest")).geometry.make_valid().union_all()
           .intersection(gp.dissolve_union(gp.microsoft_aoi())))
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)]
    cems = cems[cems.geometry.within(reg)]
    inb = bld[bld.geometry.within(reg)]
    fl = inb[inb["ms_dmg"].to_numpy(dtype="float64", na_value=0.0) == 1]
    land = gp.codab(0).geometry.make_valid().union_all()

    fll, cll = fl.to_crs(4326), cems.to_crs(4326)
    fl_cell = [h3.latlng_to_cell(p.y, p.x, RES) for p in fll.geometry]
    ca_cell = [h3.latlng_to_cell(p.y, p.x, RES) for p in cll.geometry]
    ct = cKDTree(np.c_[cems.geometry.x, cems.geometry.y])
    fl_hit = ct.query(np.c_[fl.geometry.x, fl.geometry.y], k=1)[0] <= 10
    ft = cKDTree(np.c_[fl.geometry.x, fl.geometry.y])
    ca_found30 = ft.query(np.c_[cems.geometry.x, cems.geometry.y], k=1)[0] <= 30

    F = pd.DataFrame({"cell": fl_cell, "hit": fl_hit}).groupby("cell").agg(
        n_flags=("hit", "size"), tp=("hit", "sum"))
    C = pd.DataFrame({"cell": ca_cell, "f30": ca_found30}).groupby("cell").agg(
        n_cems=("f30", "size"), found30=("f30", "sum"))
    H = F.join(C, how="outer").fillna(0)
    H["P"] = np.where(H.n_flags >= MIN_FLAGS, H.tp / H.n_flags.clip(lower=1), np.nan)
    H["vpf"] = np.where((H.n_flags >= MIN_FLAGS) & (H.found30 > 0), H.n_flags / H.found30, np.nan)

    panels = [("P", "How trustworthy are the flags here?  (precision, r = 10 m)",
               "YlOrRd", (0, max(0.4, np.nanmax(H.P))), False),
              ("vpf", "Field visits per real damaged building found  (lower = better)",
               "YlOrRd_r", (1, np.nanpercentile(H.vpf, 95)), True)]
    fig, axes = plt.subplots(2, 1, figsize=(14, 8.4))
    for ax, (col, title, cmap, vlim, rev) in zip(axes, panels):
        ax.set_facecolor("#e7f0f6")
        for g in getattr(land, "geoms", [land]):
            ax.add_patch(MplPolygon(np.asarray(g.exterior.coords), closed=True,
                                    facecolor="#f1f0ea", edgecolor="#b9b7ae", lw=0.8, zorder=0))
        cm, norm = plt.get_cmap(cmap), plt.Normalize(*vlim)
        for cell, v in H[col].items():
            p = hexpoly(cell)
            p.set(facecolor="#d9d9d9" if np.isnan(v) else cm(norm(v)),
                  edgecolor="white", lw=0.5, zorder=2)
            ax.add_patch(p)
        xs = [h3.cell_to_latlng(c)[1] for c in H.index]
        ys = [h3.cell_to_latlng(c)[0] for c in H.index]
        ax.set_xlim(min(xs) - 0.02, max(xs) + 0.02)
        ax.set_ylim(min(ys) - 0.02, max(ys) + 0.02)
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
        plt.colorbar(plt.cm.ScalarMappable(cmap=cm, norm=norm), ax=ax, shrink=0.85, pad=0.01)
        ax.set_title(title, fontsize=14)
        ax.text(0.01, 0.04, "WEST", transform=ax.transAxes, fontsize=12, weight="bold",
                color="#c62828")
        ax.text(0.97, 0.04, "EAST", transform=ax.transAxes, fontsize=12, weight="bold",
                color="#2e7d32", ha="right")
    fig.suptitle("Microsoft's performance is not one number — it flips across the coast "
                 "(grey = too few flags/points in cell)", fontsize=14, weight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "rq2j_deck_ms_hex.png"), dpi=150)
    print("wrote rq2j_deck_ms_hex.png")


if __name__ == "__main__":
    main()
