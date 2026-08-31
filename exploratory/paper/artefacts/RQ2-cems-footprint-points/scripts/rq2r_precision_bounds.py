"""RQ2r — precision lower -> upper bound per product, one frame (core region, r = 10 m).

Four references, same flags (gold building flags via the RQ8 OOF parquet = core region):
    lower bound   CEMS {2,3}                       the paper's headline reference
    +grade        CEMS {1,2,3}                     CEMS saw it, graded it below threshold
    +crowd        CEMS {2,3} u crowd-damaged       damage CEMS never mapped (MapSwipe)
    upper bound   CEMS {1,2,3} u crowd-damaged     union — each flag credited ONCE
Products only: MapSwipe voted exclusively on AI-flagged locations, so crediting the crowd
cannot fairly score the geography null or the composites (rq2n's circularity guard).

TWO crowd conventions exist in this paper's artefacts, and this CSV carries BOTH:
  * measured (rq2i's rule, and the paper's bounds figure): a flag earns credit only where
    the crowd actually reviewed its location and judged it damaged; unreviewed locations
    earn nothing. Columns P_crowd / P_upper.
  * extrapolated (rq5b's rule, @tbl-dial's crowd-adj column): the damage rate among the
    REVIEWED unmatched flags is assumed to hold for the unreviewed ones too. Columns
    P_crowd_extrap / P_upper_extrap.
They agree where crowd coverage is high (MS 98%) and diverge where it is thin (UH 27%).

Diagnostic `crowd_fp_near_class1`: of the crowd-confirmed CEMS-{2,3}-false flags, the
share within 10 m of a CEMS class-1 point — i.e. how much the two corrections are the
same buildings. Measured at 0.10–0.17: mostly DIFFERENT buildings, so the union upper
bound is nearly the additive stack and does not double-count.

ANCHORS (script raises on any miss):
  * P_floor / P_grade reproduce rq2q_incl_possibly.csv's product rows exactly;
  * P_crowd_extrap reproduces rq5b_six_member.csv's P_crowd_adj exactly.

Run: uv run --group etl --with scipy --with h3 python \
       exploratory/paper/artefacts/RQ2-cems-footprint-points/scripts/rq2r_precision_bounds.py
"""
from __future__ import annotations
import gzip, json, os, sys

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

HERE = os.path.dirname(__file__)
RQ8 = os.path.join(HERE, "..", "..", "RQ8-learned-fusion")
RQ5 = os.path.join(HERE, "..", "..", "RQ5-ensemble")
R = 10
PRODUCTS = ["MS", "IMPACT", "OSU", "UH", "LIST", "UNEP"]


def mapswipe_tasks():  # verbatim rq2i logic (frozen blobs, >=4 votes, majority class)
    import ocha_stratus as stratus
    cc = stratus.get_container_client(stage="dev", container_name=gp.S.container)
    pref = gp.S.blob_path("bronze", "source=mapswipe", "adm0=VE", event=None)
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
    t = t[t.total_count >= 4].copy()
    t["majority"] = t[["0_share", "1_share", "2_share"]].to_numpy().argmax(axis=1)
    return t.drop_duplicates(subset="h3", keep="first").set_index("h3")["majority"]


def main():
    d = pd.read_parquet(os.path.join(RQ8, "rq8_oof_scores_r10.parquet"))
    bld = gpd.GeoDataFrame(d, geometry=gpd.points_from_xy(d.lon, d.lat), crs=4326)
    bld_m = bld.to_crs(gp.METRIC_CRS)
    bxy = np.c_[bld_m.geometry.x, bld_m.geometry.y]
    cems = gp.to_metric(gp.cems_points())

    def near(classes):
        cp = cems[cems.damage_class.isin(classes)]
        return cKDTree(np.c_[cp.geometry.x, cp.geometry.y]).query(bxy, k=1)[0] <= R

    hit23, hit123, hit1 = near((2, 3)), near((1, 2, 3)), near((1,))

    tasks = mapswipe_tasks()
    print(f"MapSwipe task cells (frozen, >=4 votes): {len(tasks):,}")
    cv = np.full(len(d), np.nan)  # NaN = crowd never voted this building's cell
    for i, (lon, lat) in enumerate(zip(d.lon.to_numpy(), d.lat.to_numpy())):
        for res in (11, 12):
            c = h3.latlng_to_cell(lat, lon, res)
            if c in tasks.index:
                cv[i] = tasks.loc[c]
                break
    voted, crowd_dmg = pd.notna(cv), cv == 1

    rq2q = pd.read_csv(os.path.join(HERE, "..", "rq2q_incl_possibly.csv")
                       ).set_index(["threshold", "rule"])
    rq5b = pd.read_csv(os.path.join(RQ5, "rq5b_six_member.csv")).set_index("rule")

    rows, bad = [], []
    for p in PRODUCTS:
        fl = d[f"flag_{p}"].to_numpy(dtype="float64") == 1
        n = int(fl.sum())
        P_floor = round(float(hit23[fl].mean()), 3)
        P_grade = round(float(hit123[fl].mean()), 3)
        # measured: unreviewed flags earn nothing
        P_crowd = round(float((hit23 | crowd_dmg)[fl].mean()), 3)
        P_upper = round(float((hit123 | crowd_dmg)[fl].mean()), 3)
        # extrapolated (rq5b's rule): reviewed-FP damage rate assumed for unreviewed FPs
        fp23 = fl & ~hit23
        conf23 = float(crowd_dmg[fp23 & voted].mean())  # among REVIEWED unmatched flags
        P_crowd_x = round((hit23[fl].sum() + fp23.sum() * conf23) / n, 3)
        fp123 = fl & ~hit123
        conf123 = float(crowd_dmg[fp123 & voted].mean())
        P_upper_x = round((hit123[fl].sum() + fp123.sum() * conf123) / n, 3)
        cov = float(voted[fp23].mean())
        cc_fp = fp23 & crowd_dmg
        overlap = float(hit1[cc_fp].mean()) if cc_fp.any() else np.nan

        for got, want, what in ((P_floor, rq2q.loc[("dmg+destroyed", p), "P"], "rq2q floor"),
                                (P_grade, rq2q.loc[("incl_possibly", p), "P"], "rq2q grade"),
                                (P_crowd_x, rq5b.loc[p, "P_crowd_adj"], "rq5b crowd-adj")):
            if got != want:
                bad.append(f"{p} {what}: got {got}, frozen {want}")
        rows.append(dict(product=p, n_flags=n, P_floor=P_floor, P_grade=P_grade,
                         P_crowd=P_crowd, P_upper=P_upper,
                         P_crowd_extrap=P_crowd_x, P_upper_extrap=P_upper_x,
                         crowd_cov_of_fps=round(cov, 2),
                         crowd_fp_near_class1=round(overlap, 2) if overlap == overlap else np.nan))

    if bad:
        raise SystemExit("ANCHOR FAILED:\n  " + "\n  ".join(bad))
    print("anchors OK: floor/grade reproduce rq2q; extrapolated crowd reproduces rq5b (6 products)")

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(HERE, "..", "rq2r_precision_bounds.csv"), index=False)
    print(out.to_string(index=False))
    print("wrote rq2r_precision_bounds.csv")


if __name__ == "__main__":
    main()
