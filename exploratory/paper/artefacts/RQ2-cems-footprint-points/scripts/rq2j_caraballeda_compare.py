"""RQ2j — Caraballeda-zoomed precision hex maps, 3 products per figure (user design).

Two figures for the deck (MS/IMPACT/OSU and UH/LIST/UNEP), each 3 products stacked, all
zoomed to Caraballeda (the dense-damage zone), all on the SAME precision colour scale so
they're directly comparable. res-7 cells; grey where < 20 flags in the cell. OSU v0-pinned.

Run: uv run --group etl --with scipy --with matplotlib python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2j_caraballeda_compare.py
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
MIN_FLAGS = 20
MEMBERS = {"MS": "ms_dmg", "IMPACT": "sar_dmg", "OSU": "osu_dmg",
           "UH": "uh_dmg", "LIST": "list_dmg", "UNEP": "debris_dmg"}
GROUPS = [("MS", "IMPACT", "OSU"), ("UH", "LIST", "UNEP")]
VMAX = 0.4


def uh_aoi():
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    g = gp._read_pq("silver", "source=uh", "adm0=VE", "footprints.parquet")
    cells = {h3.latlng_to_cell(p.y, p.x, 9) for p in g.geometry.representative_point()}
    dil = set()
    for c in cells:
        dil.update(h3.grid_disk(c, 1))
    polys = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in dil]
    return gp.dissolve_union(gpd.GeoDataFrame(geometry=[unary_union(polys)], crs=4326))


def hexpoly(c):
    return MplPolygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)], closed=True)


def main():
    df = gp.building_flags(columns=["lon", "lat", *MEMBERS.values()])  # OSU v0-pinned
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                           crs=4326).to_crs(gp.METRIC_CRS)
    ext = gp.cems_extent().query("is_latest")
    car = gp.to_metric(ext[ext.aoi_name == "Caraballeda"]).geometry.make_valid().union_all()
    prod_aois = {"MS": gp.dissolve_union(gp.microsoft_aoi()),
                 "IMPACT": gp.dissolve_union(gp.impact_v2_aoi()),
                 "OSU": gp.dissolve_union(gp.osu_aoi()), "UH": uh_aoi(),
                 "LIST": gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                                       "analysed_extent.parquet")),
                 "UNEP": None}
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)]
    cems = cems[cems.geometry.within(car)]
    land = gp.codab(0).geometry.make_valid().union_all()
    ct = cKDTree(np.c_[cems.geometry.x, cems.geometry.y])

    # shared Caraballeda extent for all panels
    cll = cems.to_crs(4326)
    xlim = (cll.geometry.x.min() - 0.015, cll.geometry.x.max() + 0.015)
    ylim = (cll.geometry.y.min() - 0.012, cll.geometry.y.max() + 0.012)

    def prec_cells(col, reg):
        inb = bld[bld.geometry.within(reg)]
        fl = inb[inb[col].to_numpy(dtype="float64", na_value=0.0) == 1]
        fll = fl.to_crs(4326)
        cell = [h3.latlng_to_cell(p.y, p.x, RES) for p in fll.geometry]
        hit = ct.query(np.c_[fl.geometry.x, fl.geometry.y], k=1)[0] <= 10
        g = pd.DataFrame({"cell": cell, "hit": hit}).groupby("cell").agg(
            n=("hit", "size"), tp=("hit", "sum"))
        return {c: (r.tp / r.n if r.n >= MIN_FLAGS else np.nan) for c, r in g.iterrows()}

    for gi, group in enumerate(GROUPS, 1):
        fig, axes = plt.subplots(3, 1, figsize=(13, 9))
        cm, norm = plt.get_cmap("YlOrRd"), plt.Normalize(0, VMAX)
        for ax, nm in zip(axes, group):
            reg = car if prod_aois[nm] is None else car.intersection(prod_aois[nm])
            cells = prec_cells(MEMBERS[nm], reg)
            ax.set_facecolor("#e7f0f6")
            for g in getattr(land, "geoms", [land]):
                ax.add_patch(MplPolygon(np.asarray(g.exterior.coords), closed=True,
                                        facecolor="#f1f0ea", edgecolor="#b9b7ae", lw=0.8, zorder=0))
            for c, v in cells.items():
                p = hexpoly(c)
                p.set(facecolor="#d9d9d9" if np.isnan(v) else cm(norm(v)),
                      edgecolor="white", lw=0.5, zorder=2)
                ax.add_patch(p)
            ax.set_xlim(*xlim); ax.set_ylim(*ylim)
            ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
            ax.set_title(nm, fontsize=15, weight="bold", loc="left")
        cb = fig.colorbar(plt.cm.ScalarMappable(cmap=cm, norm=norm), ax=axes,
                          shrink=0.7, pad=0.01)
        cb.set_label("precision (share of flags on real damage, r = 10 m)", fontsize=12)
        fig.suptitle(f"Precision across Caraballeda — {' · '.join(group)}   "
                     "(same scale; grey = < 20 flags in cell)", fontsize=14, weight="bold")
        out = os.path.join(FIGS, f"rq2j_caraballeda_p{gi}.png")
        fig.savefig(out, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"wrote {os.path.basename(out)}")


if __name__ == "__main__":
    main()
