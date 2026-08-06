"""RQ2c — density-mirror null, per CEMS analysed area (the skeptic's test).

Worry (user, 2026-07-07): AI products "just mirror building density". A pure density mirror
flags x% of buildings everywhere, regardless of damage. Two discriminators, per CEMS
analysed area (aoi_name, latest):

  enrichment  = recall / flag_fraction   (density mirror => ~1; damage signal => >1)
  flag-rate contrast: a damage-sensitive product should flag FAR fewer buildings in CEMS
  areas with ~zero damage (Moron 26 pts, San Felipe 14, others 3) than in the hard-hit
  coastal strips (1,022 + 433 pts). A density mirror flags the same rate everywhere.
  precision lift = precision / random-baseline precision, where baseline = fraction of ALL
  universe buildings within r of a CEMS point (what a random flagger would score there).

Construction basis: gold building_flags (Overture centroids; same caveat as RQ5 — use for
rule/area contrasts, not absolute single-product numbers). Scoring: dual-anchor r=10 m vs
native CEMS {2,3} points. Universe per (area, product) = buildings in area ∩ product AOI.

Run: uv run --group etl --with scipy python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2_density_null.py
"""
from __future__ import annotations
import io, os, sys
import geopandas as gpd
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

POS = (2, 3)
R = 10
MEMBERS = ("ms", "impact", "osu", "uh")


def building_flags():
    import ocha_stratus as stratus
    df = gp.building_flags(columns=["id", "lon", "lat", "ms_dmg", "sar_dmg", "osu_dmg", "uh_dmg"])  # OSU pinned to v0 (paper basis)
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326)
    return g.to_crs(gp.METRIC_CRS).rename(
        columns={"ms_dmg": "dmg_ms", "sar_dmg": "dmg_impact", "osu_dmg": "dmg_osu",
                 "uh_dmg": "dmg_uh"})


def uh_aoi():
    import h3
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    g = gp._read_pq("silver", "source=uh", "adm0=VE", "footprints.parquet")
    pts = g.geometry.representative_point()
    cells = {h3.latlng_to_cell(p.y, p.x, 9) for p in pts}
    dilated = set()
    for c in cells:
        dilated.update(h3.grid_disk(c, 1))
    polys = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in dilated]
    return gp.dissolve_union(gpd.GeoDataFrame(geometry=[unary_union(polys)], crs=4326))


def main():
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)][["geometry"]]
    ext = gp.cems_extent()
    latest = gp.to_metric(ext[ext.is_latest == True])  # noqa: E712
    bld = building_flags()
    aois = {
        "ms": gp.dissolve_union(gp.microsoft_aoi()),
        "impact": gp.dissolve_union(gp.impact_v2_aoi()),
        "osu": gp.dissolve_union(gp.osu_aoi()),
        "uh": uh_aoi(),
    }
    for m, a in aois.items():
        bld[f"in_{m}"] = bld.geometry.within(a)

    rows = []
    for aoi_name, sub in latest.groupby("aoi_name"):
        area = sub.geometry.make_valid().union_all()
        in_area = bld.geometry.within(area)
        cems_a = cems[cems.geometry.within(area)]
        for m in MEMBERS:
            uni = bld[in_area & bld[f"in_{m}"]]
            if len(uni) < 500:  # product barely overlaps this area
                continue
            cems_u = cems_a[cems_a.geometry.within(aois[m])]
            flagged = uni[uni[f"dmg_{m}"] == 1]
            flag_frac = len(flagged) / len(uni)
            # random-baseline precision: share of ALL universe buildings within R of a CEMS pt
            nb, db = gp.match_rate(uni, cems_u, R)
            baseline = nb / db if db else float("nan")
            nprec, dprec = gp.match_rate(flagged, cems_u, R)
            prec = nprec / dprec if dprec else float("nan")
            nrec, drec = gp.match_rate(cems_u, flagged, R)
            rec = nrec / drec if drec else float("nan")
            rows.append(dict(
                area=aoi_name, product=m.upper(), n_bldg=len(uni), n_cems=len(cems_u),
                n_flag=len(flagged), flag_pct=round(100 * flag_frac, 1),
                recall=round(rec, 3) if drec else None,
                enrichment=round(rec / flag_frac, 1) if drec and flag_frac else None,
                precision=round(prec, 3) if dprec else None,
                rand_prec=round(baseline, 3),
                lift=round(prec / baseline, 1) if dprec and baseline else None,
            ))

    out = pd.DataFrame(rows).sort_values(["product", "n_cems"], ascending=[True, False])
    csv = os.path.join(os.path.dirname(__file__), "..", "rq2_density_null.csv")
    out.to_csv(csv, index=False)
    print(out.to_string(index=False))
    print("wrote", csv)


if __name__ == "__main__":
    main()
