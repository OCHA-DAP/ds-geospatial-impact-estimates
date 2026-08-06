"""RQ2j — hex performance maps, per product: precision / recall / F1 / visits-per-find.

The MS-call deck had res-7 hex P/R/F1 maps for Microsoft only; this generalizes to all
six members (user, 2026-07-27: "a missing step"). One figure per product, four stacked
panels on a CODAB coastline basemap:

  P (scorecard r=10), R (scorecard r=10), F1, and visits-per-verified-find at 30 m
  (flags in hex / CEMS points in hex reached within 30 m — the dial's operational cost).

Cells are res-7 (~5 km²). Grey-out: P/F1/visits need >= 20 flags in the cell; R/F1 need
>= 10 CEMS points. All maps within (CEMS latest extents ∩ product extent); OSU v0-pinned.
All figures go to the register (mechanical paper); the manuscript picks later.

Run: uv run --group etl --with scipy --with matplotlib python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2j_hex_performance_maps.py
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
MEMBERS = {"MS": "ms_dmg", "IMPACT": "sar_dmg", "OSU": "osu_dmg",
           "UH": "uh_dmg", "LIST": "list_dmg", "UNEP": "debris_dmg"}


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
    all_ext = gp.to_metric(gp.cems_extent().query("is_latest")).geometry.make_valid().union_all()
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)]
    cems = cems[cems.geometry.within(all_ext)]
    cll = cems.to_crs(4326)
    cems_cell = pd.Series([h3.latlng_to_cell(p.y, p.x, RES) for p in cll.geometry],
                          index=cems.index)
    land = gp.codab(0).geometry.make_valid().union_all()

    prod_aois = {"MS": gp.dissolve_union(gp.microsoft_aoi()),
                 "IMPACT": gp.dissolve_union(gp.impact_v2_aoi()),
                 "OSU": gp.dissolve_union(gp.osu_aoi()),
                 "UH": uh_aoi(),
                 "LIST": gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                                       "analysed_extent.parquet")),
                 "UNEP": None}

    ct_all = cKDTree(np.c_[cems.geometry.x, cems.geometry.y])
    for nm, col in MEMBERS.items():
        reg = all_ext if prod_aois[nm] is None else all_ext.intersection(prod_aois[nm])
        inb = bld[bld.geometry.within(reg)]
        fl = inb[inb[col].to_numpy(dtype="float64", na_value=0.0) == 1]
        ca = cems[cems.geometry.within(reg)]
        if not len(fl) or not len(ca):
            continue
        fll = fl.to_crs(4326)
        fl_cell = [h3.latlng_to_cell(p.y, p.x, RES) for p in fll.geometry]
        fl_hit10 = ct_all.query(np.c_[fl.geometry.x, fl.geometry.y], k=1)[0] <= 10
        ft = cKDTree(np.c_[fl.geometry.x, fl.geometry.y])
        ca_hit10 = ft.query(np.c_[ca.geometry.x, ca.geometry.y], k=1)[0] <= 10
        ca_hit30 = ft.query(np.c_[ca.geometry.x, ca.geometry.y], k=1)[0] <= 30
        ca_cell = cems_cell.loc[ca.index]

        F = pd.DataFrame({"cell": fl_cell, "hit": fl_hit10})
        C = pd.DataFrame({"cell": ca_cell.to_numpy(), "hit10": ca_hit10, "hit30": ca_hit30})
        gF = F.groupby("cell").agg(n_flags=("hit", "size"), tp=("hit", "sum"))
        gC = C.groupby("cell").agg(n_cems=("hit10", "size"), found10=("hit10", "sum"),
                                   found30=("hit30", "sum"))
        H = gF.join(gC, how="outer").fillna(0)
        H["P"] = np.where(H.n_flags >= MIN_FLAGS, H.tp / H.n_flags.clip(lower=1), np.nan)
        H["R"] = np.where(H.n_cems >= MIN_CEMS, H.found10 / H.n_cems.clip(lower=1), np.nan)
        H["F1"] = np.where(H.P.notna() & H.R.notna() & ((H.P + H.R) > 0),
                           2 * H.P * H.R / (H.P + H.R), np.nan)
        H["vpf"] = np.where((H.n_flags >= MIN_FLAGS) & (H.found30 > 0),
                            H.n_flags / H.found30, np.nan)

        panels = [("P", "precision (r = 10 m)", "YlOrRd", (0, max(0.4, np.nanmax(H.P)))),
                  ("R", "recall (r = 10 m)", "YlGnBu", (0, 1)),
                  ("F1", "F1 (r = 10 m)", "YlOrRd", (0, max(0.3, np.nanmax(H.F1)))),
                  ("vpf", "visits per verified find (30 m; lower is better)",
                   "YlOrRd", (1, np.nanpercentile(H.vpf, 95) if H.vpf.notna().any() else 10))]
        fig, axes = plt.subplots(4, 1, figsize=(11, 16))
        for ax, (colk, title, cmap, vlim) in zip(axes, panels):
            ax.set_facecolor("#e7f0f6")
            for g in getattr(land, "geoms", [land]):
                ax.add_patch(MplPolygon(np.asarray(g.exterior.coords), closed=True,
                                        facecolor="#f1f0ea", edgecolor="#b9b7ae",
                                        lw=0.8, zorder=0))
            vals = H[colk]
            norm = plt.Normalize(*vlim)
            cm = plt.get_cmap(cmap)
            for cell, v in vals.items():
                p = hexpoly(cell)
                if np.isnan(v):
                    p.set(facecolor="#d9d9d9", edgecolor="white", lw=0.4, zorder=2)
                else:
                    p.set(facecolor=cm(norm(v)), edgecolor="white", lw=0.4, zorder=2)
                ax.add_patch(p)
            xs = [h3.cell_to_latlng(c)[1] for c in H.index]
            ys = [h3.cell_to_latlng(c)[0] for c in H.index]
            ax.set_xlim(min(xs) - 0.03, max(xs) + 0.03)
            ax.set_ylim(min(ys) - 0.03, max(ys) + 0.03)
            ax.set_aspect("equal")
            ax.set_xticks([]); ax.set_yticks([])
            sm = plt.cm.ScalarMappable(cmap=cm, norm=norm)
            plt.colorbar(sm, ax=ax, shrink=0.8, pad=0.01)
            ax.set_title(f"{nm} — {title}", fontsize=12)
        fig.suptitle(f"{nm}: hex-cell performance (res-7 ≈ 5 km²; grey = too little data "
                     f"in cell:\n< {MIN_FLAGS} flags for precision/visits, < {MIN_CEMS} "
                     f"CEMS points for recall; region = CEMS ∩ product extent)",
                     fontsize=12)
        fig.tight_layout()
        out = os.path.join(FIGS, f"rq2j_hexperf_{nm.lower()}.png")
        fig.savefig(out, dpi=140)
        plt.close(fig)
        print(f"wrote {os.path.basename(out)} | cells: {len(H):,} "
              f"(P shown in {int(H.P.notna().sum())}, R in {int(H.R.notna().sum())})")


if __name__ == "__main__":
    main()
