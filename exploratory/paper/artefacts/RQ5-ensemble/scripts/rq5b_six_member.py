"""RQ5b — six-member ensemble, triple-referenced (decision 2026-07-15).

Members: MS, IMPACT v2, OSU, UH, LIST (WFP/LIST/CERN ResNet pre/post; has analysed extent),
UNEP debris (no AOI; USER DECISION: treated as fully covering the core region — same
enclosure logic as RQ4; stated assumption). IMPACT v1 dropped (user).

Core region = CEMS latest extent ∩ the five available AOIs (MS, IMPACT, OSU, UH, LIST).
Rules: 6 singles + k-of-6 (k=1..6) + benchmark pairs (same-sensor IMPACT∧OSU vs cross pairs).
Every rule scored against ALL THREE references in one table:
  - CEMS: dual-anchor precision(floor)/recall/F1, r=10 m
  - ChatMap field points: recall r=20 m (miss-side)
  - MapSwipe crowd: share of CEMS-unmatched flags in majority-DAMAGED hexes (>=4 votes)
    -> crowd-adjusted precision (as RQ7b)

Run: uv run --group etl --with scipy python \
       exploratory/paper/artefacts/RQ5-ensemble/scripts/rq5b_six_member.py
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
R_CEMS, R_FIELD = 10, 20
MIN_VOTES = 4
MEMBERS = {"MS": "ms_dmg", "IMPACT": "sar_dmg", "OSU": "osu_dmg",
           "UH": "uh_dmg", "LIST": "list_dmg", "UNEP": "debris_dmg"}
PAIRS = [("IMPACT", "OSU"), ("MS", "UH"), ("MS", "LIST"), ("LIST", "UH"),
         ("UNEP", "OSU"), ("MS", "UNEP")]


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
    import ocha_stratus as stratus
    cc = stratus.get_container_client(stage="dev", container_name=gp.S.container)
    pref = gp.S.blob_path("bronze", "source=mapswipe", "adm0=VE")
    frames = []
    for b in cc.list_blobs(name_starts_with=pref):
        if not gp.mapswipe_is_frozen(b.name):
            continue  # post-freeze round-2 re-vote (see gie_paper.MAPSWIPE_POSTFREEZE)
        if "agg_results_by_task" in b.name and b.name.endswith(".geojson.gz"):
            feats = json.loads(gzip.decompress(cc.download_blob(b.name).readall()))["features"]
            rows = [f["properties"] for f in feats if f["properties"].get("h3")]
            if rows:
                frames.append(pd.DataFrame(rows))
    t = pd.concat(frames, ignore_index=True)
    t = t[t.total_count >= MIN_VOTES].copy()
    t["majority"] = t[["0_share", "1_share", "2_share"]].to_numpy().argmax(axis=1)
    return t.drop_duplicates(subset="h3", keep="first").set_index("h3")[["majority", "res"]]


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
    field = gpd.GeoDataFrame.from_features(json.loads(stratus.load_blob_data(
        gp.S.blob_path("bronze", "source=mapswipe", "adm0=VE", "hdx",
                       "chatmap_field_validated_damage_points.geojson"),
        stage="dev", container_name=gp.S.container))["features"], crs=4326).to_crs(gp.METRIC_CRS)
    fpts = field[field.geometry.within(region)]
    tasks = mapswipe_tasks()
    print(f"core region: {region.area/1e6:.1f} km2 | buildings {in_reg.sum():,} | "
          f"CEMS pts {len(cpts):,} | field pts {len(fpts):,} | crowd tasks {len(tasks):,}")

    def crowd_verdicts(sub4326):
        out = []
        for p in sub4326.geometry:
            for res in (11, 12):
                c = h3.latlng_to_cell(p.y, p.x, res)
                if c in tasks.index:
                    out.append(int(tasks.loc[c, "majority"]))
                    break
        return pd.Series(out)

    rules = [(nm, bld[in_reg & (df[col] == 1)]) for nm, col in MEMBERS.items()]
    rules += [(f"{a}∧{b_}", bld[in_reg & (df[MEMBERS[a]] == 1) & (df[MEMBERS[b_]] == 1)])
              for a, b_ in PAIRS]
    rules += [(f"{k}-of-6", bld[in_reg & (votes >= k)]) for k in range(1, 7)]

    rows = []
    for nm, flagged in rules:
        nr, dr = gp.match_rate(cpts, flagged, R_CEMS)
        np_, dp = gp.match_rate(flagged, cpts, R_CEMS)
        rec = nr / dr if dr else np.nan
        prec = np_ / dp if dp else np.nan
        f1 = 2 * prec * rec / (prec + rec) if (prec or 0) + (rec or 0) > 0 else 0
        nf, dfld = gp.match_rate(fpts, flagged, R_FIELD)
        # crowd adjudication of CEMS-unmatched flags
        j = gpd.sjoin_nearest(flagged[["geometry"]], cpts, max_distance=R_CEMS,
                              how="left", distance_col="_d")
        j = j[~j.index.duplicated()]
        fp_idx = j[j["_d"].isna()].index
        v = crowd_verdicts(bld.loc[fp_idx].to_crs(4326)) if len(fp_idx) else pd.Series(dtype=int)
        conf = (v == 1).mean() if len(v) else np.nan
        p_adj = (np_ + len(fp_idx) * (conf if conf == conf else 0)) / dp if dp else np.nan
        rows.append(dict(rule=nm, flagged=len(flagged),
                         P_cems=round(prec, 3), R_cems=round(rec, 3), F1_cems=round(f1, 3),
                         R_field_r20=round(nf / dfld, 2) if dfld else np.nan,
                         FP_crowd_damaged=round(conf, 2) if conf == conf else np.nan,
                         P_crowd_adj=round(p_adj, 3) if p_adj == p_adj else np.nan))
        print(rows[-1], flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(HERE, "..", "rq5b_six_member.csv"), index=False)
    print("wrote rq5b_six_member.csv")


if __name__ == "__main__":
    main()
