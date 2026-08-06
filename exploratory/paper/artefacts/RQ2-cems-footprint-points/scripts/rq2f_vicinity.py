"""RQ2f — multi-scale matching: building identity vs "got the responder to the damage".

The fabric caps building-identity matching at r≈10 m (median nearest-neighbour spacing
9.7 m in Caraballeda). Larger radii answer a DIFFERENT, operationally legitimate question:
did the mapped point put a responder where damage is visible/findable? Scales:

  r=10   building identity ("this building")
  r=30   line-of-sight ("stand at the point, see the damaged building")
  r=60   same block ("find it in a minute's walk")
  r=100  right area
  + H3 res-11 cell agreement (~50 m hex) — the HOT/MapSwipe areal unit, directly
    comparable to their own agreement analysis.

Per rule × scale, in the frozen core region (six members, CEMS latest-only):
  found_rate  = share of CEMS {2,3} points with a flag within r  (recall at that scale)
  wasted_trip = share of flags with NO CEMS point within r (upper bound — CEMS floor;
                some "wasted trips" are CEMS gaps per RQ7b)
H3 version: cells containing >=1 flag vs cells containing >=1 CEMS point.

Run: uv run --group etl --with scipy --with matplotlib python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2f_vicinity.py
"""
from __future__ import annotations
import io, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
FIGS = os.path.join(HERE, "..", "figs")
POS = (2, 3)
RADII = (10, 30, 60, 100)
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


def main():
    import ocha_stratus as stratus
    df = gp.building_flags(columns=["lon", "lat", *MEMBERS.values()])  # OSU pinned to v0 (paper basis)
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                           crs=4326).to_crs(gp.METRIC_CRS)
    votes = df[list(MEMBERS.values())].sum(axis=1)

    region = gp.to_metric(gp.cems_extent().query("is_latest")).geometry.make_valid().union_all()
    for a in (gp.dissolve_union(gp.microsoft_aoi()), gp.dissolve_union(gp.impact_v2_aoi()),
              gp.dissolve_union(gp.osu_aoi()), uh_aoi(),
              gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                            "analysed_extent.parquet"))):
        region = region.intersection(a)
    in_reg = bld.geometry.within(region)
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)][["geometry"]]
    cpts = cems[cems.geometry.within(region)]
    cpts_ll = cpts.to_crs(4326)
    cems_cells = {h3.latlng_to_cell(p.y, p.x, 11) for p in cpts_ll.geometry}
    print(f"region buildings {in_reg.sum():,} | CEMS pts {len(cpts):,} | "
          f"CEMS res-11 cells {len(cems_cells):,}")

    rules = [(nm, df[col] == 1) for nm, col in MEMBERS.items()]
    rules += [(f"{k}-of-6", votes >= k) for k in (1, 3, 4, 6)]

    rows = []
    for nm, mask in rules:
        flagged = bld[in_reg & mask]
        row = dict(rule=nm, flagged=len(flagged))
        for r in RADII:
            nf, dfound = gp.match_rate(cpts, flagged, r)
            nw, dw = gp.match_rate(flagged, cpts, r)
            row[f"found_r{r}"] = round(nf / dfound, 2) if dfound else np.nan
            row[f"wasted_r{r}"] = round(1 - nw / dw, 2) if dw else np.nan
        # H3 res-11 cell agreement (the HOT/MapSwipe unit)
        fl = flagged.to_crs(4326)
        fcells = {h3.latlng_to_cell(p.y, p.x, 11) for p in fl.geometry}
        inter = len(fcells & cems_cells)
        row["h3_found"] = round(inter / len(cems_cells), 2)
        row["h3_wasted"] = round(1 - inter / len(fcells), 2) if fcells else np.nan
        row["h3_cells"] = len(fcells)
        rows.append(row)
        print(row, flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(HERE, "..", "rq2f_vicinity.csv"), index=False)
    print("wrote rq2f_vicinity.csv")

    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6), sharex=True)
    show = ("MS", "OSU", "LIST", "3-of-6", "4-of-6")
    for nm in show:
        r_ = out[out.rule == nm].iloc[0]
        ax[0].plot(RADII, [r_[f"found_r{r}"] for r in RADII], "-o", ms=4, label=nm)
        ax[1].plot(RADII, [r_[f"wasted_r{r}"] for r in RADII], "-o", ms=4, label=nm)
    for a, t in ((ax[0], "found rate — share of CEMS damage with a flag within r"),
                 (ax[1], "wasted-trip rate (CEMS floor) — share of flags with no damage within r")):
        a.set_title(t, fontsize=10)
        a.set_xlabel("matching radius r (m)")
        a.axvline(10, ls=":", c="grey"); a.annotate("building\nidentity", (11, 0.05), fontsize=8)
        a.axvline(30, ls=":", c="grey"); a.annotate("line of\nsight", (32, 0.05), fontsize=8)
        a.set_ylim(0, 1)
    ax[0].legend(fontsize=8)
    fig.suptitle("RQ2f — the same flags, different questions: identity (r=10) vs vicinity success")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "rq2f_vicinity_curves.png"), dpi=130)
    print("wrote figs/rq2f_vicinity_curves.png")


if __name__ == "__main__":
    main()
