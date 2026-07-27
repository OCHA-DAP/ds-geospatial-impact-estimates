"""RQ3 prioritization map — do products point at the right neighbourhoods?

The rank scatter buries the finding (log-log noise). This shows it directly: res-7
triage cells (~5 km2) shaded by REAL damage (CEMS {2,3} count), with each product's
own top-N worst-hit picks outlined in bold. Overlap = the product sent you to the right
places. Best-case frame (Caraballeda, where the ranking is measurable). OSU v0-pinned.

Run: uv run --group etl --with matplotlib python \
       exploratory/paper/artefacts/RQ3-prioritization-error-structure/scripts/rq3_priority_map_fig.py
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
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
TOPN = 20
PRODUCTS = [("Microsoft", "ms_dmg"), ("OSU", "osu_dmg")]


def hexpoly(c):
    return MplPolygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)], closed=True)


def main():
    df = gp.building_flags(columns=["lon", "lat", "ms_dmg", "osu_dmg"])  # OSU v0-pinned
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326)
    # Caraballeda AOI (the dense-reference zone where ranking is measurable)
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
    truth = cems_ct.reindex(cells).fillna(0)
    truth_top = set(truth.sort_values(ascending=False).head(TOPN).index)
    land = gp.codab(0).geometry.make_valid().union_all()

    fig, axes = plt.subplots(len(PRODUCTS), 1, figsize=(11, 9))
    vmax = float(truth.max())
    for ax, (nm, col) in zip(axes, PRODUCTS):
        pc = inb[inb[col].to_numpy(dtype="float64", na_value=0.0) == 1].groupby("cell").size()
        prod = pc.reindex(cells).fillna(0)
        prod_top = set(prod.sort_values(ascending=False).head(TOPN).index)
        hit = len(truth_top & prod_top)

        ax.set_facecolor("#e7f0f6")
        for g in getattr(land, "geoms", [land]):
            ax.add_patch(MplPolygon(np.asarray(g.exterior.coords), closed=True,
                                    facecolor="#f1f0ea", edgecolor="#b9b7ae", lw=0.8, zorder=0))
        cm = plt.get_cmap("YlOrRd")
        norm = plt.Normalize(0, vmax)
        for c in cells:
            p = hexpoly(c)
            p.set(facecolor=cm(norm(truth[c])), zorder=2,
                  edgecolor=("#1841a0" if c in prod_top else "white"),
                  lw=(3.2 if c in prod_top else 0.4))
            ax.add_patch(p)
        xs = [h3.cell_to_latlng(c)[1] for c in cells]
        ys = [h3.cell_to_latlng(c)[0] for c in cells]
        ax.set_xlim(min(xs) - 0.02, max(xs) + 0.02)
        ax.set_ylim(min(ys) - 0.02, max(ys) + 0.02)
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
        sm = plt.cm.ScalarMappable(cmap=cm, norm=norm)
        plt.colorbar(sm, ax=ax, shrink=0.8, pad=0.01, label="real damage (CEMS points / cell)")
        ax.set_title(f"{nm}: found {hit} of the {TOPN} worst-hit neighbourhoods "
                     f"({hit/TOPN:.0%})", fontsize=13)
    fig.suptitle("Products point at the right neighbourhoods\n"
                 "cells shaded by REAL damage; blue outline = the product's own top-20 "
                 "worst-hit picks (res-7 ≈ 5 km², Caraballeda)", fontsize=12.5)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "rq3_priority_map.png"), dpi=150)
    print(f"wrote rq3_priority_map.png | truth top-{TOPN} cells: {len(truth_top)}")


if __name__ == "__main__":
    main()
