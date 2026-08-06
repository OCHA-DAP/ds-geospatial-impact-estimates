"""RQ2h — OSU v0 vs v1: did the provider's revision change real-world accuracy?

OSU delivered a revised product (v1: 69,431 flags, confidence tiers, expanded coverage)
on 2026-07-22, a week after the paper's data freeze. The paper scores v0 throughout —
the delivery available during the response (see gie_paper.building_flags docstring) —
and this script is the dedicated comparison. Both versions are id-keyed to the same
Overture base (silver is version-partitioned), so the comparison is exact per building.

Scored identically for each version: dual-anchor vs CEMS latest {2,3} (r = 10 m) within
CEMS ∩ that version's own analysed extent; field recall vs ChatMap (r = 20 m) within the
extent; plus a common-extent (v0 ∩ v1 ∩ CEMS) head-to-head so coverage expansion cannot
masquerade as accuracy change.

Run: uv run --group etl --with scipy python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2h_osu_v0_v1.py
"""
from __future__ import annotations
import io, json, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
POS = (2, 3)
R_CEMS, R_FIELD = 10, 20


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
    import ocha_stratus as stratus
    # geometry lookup: the shared Overture base (id -> lon/lat), version-neutral
    base = gp.building_flags(columns=["lon", "lat"])
    base = gpd.GeoDataFrame(base, geometry=gpd.points_from_xy(base.lon, base.lat),
                            crs=4326).to_crs(gp.METRIC_CRS).set_index("id")

    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)][["geometry"]]
    cems_ext = gp.to_metric(gp.cems_extent().query("is_latest")).geometry.make_valid().union_all()
    field = gpd.GeoDataFrame.from_features(json.loads(stratus.load_blob_data(
        gp.S.blob_path("bronze", "source=mapswipe", "adm0=VE", "hdx",
                       "chatmap_field_validated_damage_points.geojson"),
        stage="dev", container_name=gp.S.container))["features"], crs=4326).to_crs(gp.METRIC_CRS)

    flags, exts = {}, {}
    for v in ("v0", "v1"):
        dmg = _silver(v, "building_damage.parquet")
        ids = [i for i in dmg.id if i in base.index]
        flags[v] = base.loc[ids]
        exts[v] = gp.to_metric(_silver(v, "analysed_extent.parquet")).geometry.make_valid().union_all()
        print(f"{v}: {len(dmg):,} silver flags ({len(ids):,} on base) | "
              f"extent {exts[v].area/1e6:.0f} km2")

    def score(fl, region):
        fin = fl[fl.geometry.within(region)]
        cpts = cems[cems.geometry.within(region)]
        fpts = field[field.geometry.within(region)]
        ft = cKDTree(np.c_[fin.geometry.x, fin.geometry.y])
        ct = cKDTree(np.c_[cpts.geometry.x, cpts.geometry.y])
        prec = (ct.query(np.c_[fin.geometry.x, fin.geometry.y], k=1)[0] <= R_CEMS).mean()
        rec = (ft.query(np.c_[cpts.geometry.x, cpts.geometry.y], k=1)[0] <= R_CEMS).mean()
        frec = (ft.query(np.c_[fpts.geometry.x, fpts.geometry.y], k=1)[0] <= R_FIELD).mean()
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
        return dict(flags=len(fin), cems_pts=len(cpts), P=round(prec, 3), R=round(rec, 3),
                    F1=round(f1, 3), field_pts=len(fpts), R_field=round(frec, 2))

    rows = []
    for v in ("v0", "v1"):
        r = score(flags[v], cems_ext.intersection(exts[v]))
        rows.append(dict(version=f"{v} (own extent ∩ CEMS)", **r))
        print(rows[-1])
    common = cems_ext.intersection(exts["v0"]).intersection(exts["v1"])
    for v in ("v0", "v1"):
        r = score(flags[v], common)
        rows.append(dict(version=f"{v} (common extent)", **r))
        print(rows[-1])

    # churn on the common building set
    s0, s1 = set(flags["v0"].index), set(flags["v1"].index)
    print(f"\nflag churn: kept {len(s0 & s1):,} | dropped by v1 {len(s0 - s1):,} | "
          f"added by v1 {len(s1 - s0):,}")

    pd.DataFrame(rows).to_csv(os.path.join(HERE, "..", "rq2h_osu_v0_v1.csv"), index=False)
    print("wrote rq2h_osu_v0_v1.csv")


if __name__ == "__main__":
    main()
