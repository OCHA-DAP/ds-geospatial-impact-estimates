"""RQ7b — crowd adjudication of consensus "false positives": is ensemble precision a floor?

TERMINOLOGY (fixed): "k-of-4 vote" = a RULE flagging a building when >=k of the 4 AOI
products (MS, IMPACT v2, OSU, UH) flag it. Never a performance number.

RQ5 measured k-of-4 precision against CEMS (3-of-4: P=0.20; 4-of-4: P=0.52). RQ2e proved
CEMS itself misses lighter damage (49% of field-reported 'significant'), so CEMS-measured
precision is a FLOOR. This script measures how much of the "false positive" mass is actually
crowd-confirmed damage:

  1. Flag buildings by k-of-4 vote inside the quad region (all four AOIs ∩ CEMS extent).
  2. Split: CEMS-matched (CEMS {2,3} point within 10 m) vs CEMS-unmatched ("FP by CEMS").
  3. Join CEMS-unmatched buildings to MapSwipe task hexes (H3 index match at each project's
     resolution; vote depth >= 4 required). Crowd verdict per hex = majority of 0/1/2.
  4. Report: share of adjudicated "FPs" in majority-DAMAGED hexes (=> real damage CEMS
     missed), majority-NO hexes (=> genuine FP), majority-UNSURE. Calibration: same join for
     the CEMS-matched set (crowd confirm rate on known-good flags = upper anchor).
  5. Adjusted precision under the stated assumption (majority-damaged hex => real):
     P_adj = (TP + FP*conf_share) / flagged.

Run: uv run --group etl --with scipy python \
       exploratory/paper/artefacts/RQ7-mapswipe-validation/scripts/rq7_consensus_fp_adjudication.py
"""
from __future__ import annotations
import gzip, io, json, os, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import h3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
POS = (2, 3)
R = 10
MIN_VOTES = 4


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


def mapswipe_tasks():
    """All bronze MapSwipe validate tasks with an h3 index: h3 -> (majority, res, depth)."""
    import ocha_stratus as stratus
    cc = stratus.get_container_client(stage="dev", container_name=gp.S.container)
    pref = gp.S.blob_path("bronze", "source=mapswipe", "adm0=VE")
    frames = []
    for b in cc.list_blobs(name_starts_with=pref):
        if not gp.mapswipe_is_frozen(b.name):
            continue  # post-freeze round-2 re-vote (see gie_paper.MAPSWIPE_POSTFREEZE)
        if "agg_results_by_task" not in b.name or not b.name.endswith(".geojson.gz"):
            continue
        raw = gzip.decompress(cc.download_blob(b.name).readall())
        feats = json.loads(raw)["features"]
        rows = [f["properties"] for f in feats if f["properties"].get("h3")]
        if rows:
            frames.append(pd.DataFrame(rows))
    t = pd.concat(frames, ignore_index=True)
    t = t[t.total_count >= MIN_VOTES].copy()
    t["majority"] = t[["0_share", "1_share", "2_share"]].to_numpy().argmax(axis=1)
    t = t.drop_duplicates(subset="h3", keep="first")  # overlapping re-runs: keep first
    print(f"MapSwipe tasks with h3 + >={MIN_VOTES} votes: {len(t):,} "
          f"(res: {dict(t.res.value_counts())})")
    return t.set_index("h3")[["majority", "res"]]


def main():
    import ocha_stratus as stratus
    df = gp.building_flags(columns=["lon", "lat", "ms_dmg", "sar_dmg", "osu_dmg", "uh_dmg"])  # OSU pinned to v0 (paper basis)
    bld = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat),
                           crs=4326).to_crs(gp.METRIC_CRS)
    bld["votes"] = df[["ms_dmg", "sar_dmg", "osu_dmg", "uh_dmg"]].sum(axis=1)

    quad = gp.dissolve_union(gp.microsoft_aoi())
    for a in (gp.dissolve_union(gp.impact_v2_aoi()), gp.dissolve_union(gp.osu_aoi()), uh_aoi()):
        quad = quad.intersection(a)
    ext = gp.cems_extent()
    region = quad.intersection(
        gp.to_metric(ext[ext.is_latest == True]).geometry.make_valid().union_all())  # noqa: E712
    cems = gp.to_metric(gp.cems_points())
    cems = cems[cems.damage_class.isin(POS)][["geometry"]]

    tasks = mapswipe_tasks()
    in_reg = bld.geometry.within(region)
    ll = bld[in_reg].to_crs(4326)
    cells = {res: [h3.latlng_to_cell(p.y, p.x, res) for p in ll.geometry]
             for res in sorted(tasks.res.unique())}

    rows = []
    for k in (3, 4):
        flagged = bld[in_reg & (bld.votes >= k)]
        j = gpd.sjoin_nearest(flagged[["geometry"]], cems, max_distance=R,
                              how="left", distance_col="_d")
        j = j[~j.index.duplicated()]
        tp_idx = j[j["_d"].notna()].index
        fp_idx = j[j["_d"].isna()].index
        out = {"rule": f"{k}-of-4 vote", "flagged": len(flagged),
               "cems_matched_TP": len(tp_idx), "cems_unmatched_FP": len(fp_idx)}
        for label, idx in (("FP", fp_idx), ("TP", tp_idx)):
            sub = bld.loc[idx].to_crs(4326)
            verdicts = []
            for p in sub.geometry:
                for res in cells:
                    c = h3.latlng_to_cell(p.y, p.x, res)
                    if c in tasks.index:
                        verdicts.append(int(tasks.loc[c, "majority"]))
                        break
            v = pd.Series(verdicts)
            n = len(v)
            out[f"{label}_adjudicated"] = n
            if n:
                out[f"{label}_crowd_damaged"] = round((v == 1).mean(), 2)
                out[f"{label}_crowd_no"] = round((v == 0).mean(), 2)
                out[f"{label}_crowd_unsure"] = round((v == 2).mean(), 2)
        # adjusted precision: assume crowd-majority-damaged FPs are real damage
        conf = out.get("FP_crowd_damaged", 0) or 0
        p_floor = out["cems_matched_TP"] / out["flagged"]
        p_adj = (out["cems_matched_TP"] + out["cems_unmatched_FP"] * conf) / out["flagged"]
        out["precision_cems_floor"] = round(p_floor, 3)
        out["precision_crowd_adjusted"] = round(p_adj, 3)
        rows.append(out)
        print(out)

    pd.DataFrame(rows).to_csv(os.path.join(HERE, "..", "rq7_consensus_fp_adjudication.csv"),
                              index=False)
    print("wrote rq7_consensus_fp_adjudication.csv")


if __name__ == "__main__":
    main()
