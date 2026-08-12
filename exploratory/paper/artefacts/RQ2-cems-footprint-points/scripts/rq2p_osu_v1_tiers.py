"""RQ2p — OSU v1's confidence tiers: does the most confident class escape the ceiling?

v1 (post-freeze, 2026-07-22) replaced v0's saturated continuous damage_probability
(51% of flags at exactly 1.0) with three ordinal certainty tiers; building_damage
carries the two damaged tiers (probable / high_confidence). This scores each tier
cut with the frozen RQ2h/RQ5b method (dual-anchor vs CEMS latest {2,3}, r = 10 m)
in three regions: v1's own extent ∩ CEMS, the v0∩v1∩CEMS common extent (the RQ2h
frame), and the paper's core region (the RQ5b frame, CEMS ∩ five product AOIs,
core-region construction copied verbatim from rq5b_six_member.py). The v0 all-flags
row in the core region is the reproduction anchor: it must match the frozen rq5b
OSU row (P 0.045, R 0.688).

Run: uv run --group etl --with scipy --with h3 python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2p_osu_v1_tiers.py
"""
from __future__ import annotations
import io, os, sys
import geopandas as gpd
import h3
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
POS = (2, 3)
R_CEMS = 10


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


def _silver(version, name):
    import ocha_stratus as stratus
    b = stratus.load_blob_data(
        gp.S.blob_path("silver", "source=osu", "adm0=VE", f"version={version}", name),
        stage="dev", container_name=gp.S.container)
    try:
        return gpd.read_parquet(io.BytesIO(b))
    except ValueError:
        return pd.read_parquet(io.BytesIO(b))


def main():
    base = gp.building_flags(columns=["lon", "lat", "osu_dmg"])
    bld = gpd.GeoDataFrame(base, geometry=gpd.points_from_xy(base.lon, base.lat),
                           crs=4326).to_crs(gp.METRIC_CRS).set_index("id")

    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)][["geometry"]]
    cems_ext = gp.to_metric(gp.cems_extent().query("is_latest")).geometry.make_valid().union_all()

    core = cems_ext
    for a in (gp.dissolve_union(gp.microsoft_aoi()), gp.dissolve_union(gp.impact_v2_aoi()),
              gp.dissolve_union(gp.osu_aoi()), uh_aoi(),
              gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE",
                                            "analysed_extent.parquet"))):
        core = core.intersection(a)

    ext_v0 = gp.to_metric(_silver("v0", "analysed_extent.parquet")).geometry.make_valid().union_all()
    ext_v1 = gp.to_metric(_silver("v1", "analysed_extent.parquet")).geometry.make_valid().union_all()
    regions = {
        "v1 own extent ∩ CEMS": cems_ext.intersection(ext_v1),
        "common extent (v0∩v1∩CEMS)": cems_ext.intersection(ext_v0).intersection(ext_v1),
        "core region": core,
    }

    v1 = _silver("v1", "building_damage.parquet")
    cuts = {
        "v0 all flags (paper basis)": bld.index[bld.osu_dmg == 1],
        "v1 high_confidence only": v1[v1.damage_confidence == "high_confidence"].id,
        "v1 probable only": v1[v1.damage_confidence == "probable"].id,
        "v1 published headline (prob+high)": v1.id,
    }

    rows = []
    for region_name, region in regions.items():
        cpts = cems[cems.geometry.within(region)]
        for cut_name, ids in cuts.items():
            fl = bld.loc[[i for i in ids if i in bld.index]]
            fin = fl[fl.geometry.within(region)]
            nr, dr = gp.match_rate(cpts, fin, R_CEMS)
            np_, dp = gp.match_rate(fin, cpts, R_CEMS)
            prec, rec = np_ / dp if dp else 0, nr / dr if dr else 0
            f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
            rows.append(dict(region=region_name, cut=cut_name, flags=len(fin),
                             cems_pts=len(cpts), P=round(prec, 3), R=round(rec, 3),
                             F1=round(f1, 3)))
            print(rows[-1])

    pd.DataFrame(rows).to_csv(os.path.join(HERE, "..", "rq2p_osu_v1_tiers.csv"), index=False)
    print("wrote rq2p_osu_v1_tiers.csv")


if __name__ == "__main__":
    main()
