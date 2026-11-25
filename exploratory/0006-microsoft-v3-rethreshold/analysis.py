"""Microsoft merged v3 against the v1 the brief scores: what changed, and how it scores.

Microsoft sent a v3 of the merged Venezuela file (received 2026-09-04): v2 removed 3,912
overlapping duplicate footprints; v3 re-thresholds `damaged` to damage_pct_0m >= 0.8 for
records whose primary scene is the Catia La Mar Vantor image. This entry is auxiliary: the
viewer and the brief keep scoring v1, and nothing here writes to the lake or to
exploratory/paper/.

Steps
  1. Decompose v1 -> v3 record by record (key: source_file + orig_id) and assert the change is
     exactly what Microsoft described.
  2. Map each version's damaged footprints onto the shared Overture base with the paper's rule
     (ADR-0030; a copy of lib/build_footprint_maps.map_product that writes nothing).
  3. Gate: the v1 mapping must equal lib/ms_1to1_ids.csv, and the v1 scores must equal the MS
     rows of exploratory/paper/results.csv. Any difference stops the run.
  4. Score both versions with the paper's own scorecard functions (points frame, CEMS
     damaged+destroyed, 10 m): core region, as delivered, per CEMS area, the Caraballeda strip,
     then by primary scene and by number of observing scenes.

Run from the repo root (needs the Overture base cache, see exploratory/paper/README.md):
  uv run --group etl python exploratory/0006-microsoft-v3-rethreshold/analysis.py \
      --v3 /path/to/ALL_AOIS_building_predictions_deduplicated_v3.gpkg
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import sys
import warnings

warnings.filterwarnings("ignore")
import geopandas as gpd
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.join(HERE, "..", "paper")
sys.path[:0] = [os.path.join(PAPER, "pipeline"), os.path.join(PAPER, "lib")]
import ocha_stratus as stratus  # noqa: E402
import paperlib as pl  # noqa: E402
import scorecards as sc  # noqa: E402
from paperlib import gp  # noqa: E402

V3_SHA256 = "2d53b4a14a5723b81ac3f58da2ec8ca49b69876738a220a3cb9d6149ea0a5ef3"
V1_BLOB = gp.S.blob_path("bronze", "source=microsoft", "adm0=VE", "merged",
                         "ALL_AOIS_building_predictions_deduplicated.gpkg", event=None)
RETHRESHOLD_SCENE = "catia_la_mar_vantor_6-25_building_predictions_merged.gpkg"
RETHRESHOLD = 0.8
SNAP_M = 20
KEY = ["source_file", "orig_id"]
OUT = os.path.join(HERE, "figs")          # git-ignored; the tables live in findings.md


# ---------------------------------------------------------------- load
def load_versions(v3_path: str):
    sha = hashlib.sha256(open(v3_path, "rb").read()).hexdigest()
    if sha != V3_SHA256:
        raise SystemExit(f"v3 file hash {sha[:16]}… is not the file this entry documents ({V3_SHA256[:16]}…)")
    v1 = gpd.read_file(io.BytesIO(stratus.load_blob_data(V1_BLOB, stage="dev", container_name=gp.S.container)))
    v3 = gpd.read_file(v3_path)
    return v1, v3


# ---------------------------------------------------------------- 1. decomposition
def decompose(v1, v3) -> pd.DataFrame:
    m = v1.drop(columns="geometry").merge(v3.drop(columns="geometry"), on=KEY, how="outer",
                                          suffixes=("_1", "_3"), indicator=True)
    dropped, both = m[m._merge == "left_only"], m[m._merge == "both"]
    if (m._merge == "right_only").any():
        raise SystemExit("v3 holds records absent from v1; the change is not what Microsoft described")
    if (both.damage_pct_0m_1.fillna(-1) != both.damage_pct_0m_3.fillna(-1)).any():
        raise SystemExit("damage_pct_0m changed between versions; expected only the threshold to move")
    flip = both[both.damaged_1 != both.damaged_3]
    if not (flip.source_file == RETHRESHOLD_SCENE).all() or not (flip.damaged_1 == 1).all():
        raise SystemExit("flag changes outside the re-thresholded scene, or 0 -> 1 flips")
    scene = v3[v3.source_file == RETHRESHOLD_SCENE]
    if not ((scene.damage_pct_0m >= RETHRESHOLD).astype(int) == scene.damaged).all():
        raise SystemExit(f"v3 {RETHRESHOLD_SCENE}: damaged != (damage_pct_0m >= {RETHRESHOLD})")
    other1 = v1[v1.source_file != RETHRESHOLD_SCENE]
    if not ((other1.damage_pct_0m > 0).astype(int) == other1.damaged).all():
        raise SystemExit("v1 rule is not damaged = damage_pct_0m > 0 outside the re-thresholded scene")
    rows = [("v1 records", len(v1)), ("v3 records", len(v3)),
            ("removed as duplicates", len(dropped)), ("  of which flagged damaged in v1", int(dropped.damaged_1.sum())),
            ("flags switched off by the re-threshold", len(flip)),
            ("v1 damaged", int(v1.damaged.sum())), ("v3 damaged", int(v3.damaged.sum()))]
    t = pd.DataFrame(rows, columns=["item", "n"])
    if t.n[5] - t.n[3] - t.n[4] != t.n[6]:
        raise SystemExit("v1 damaged − removed − switched off ≠ v3 damaged")
    by_scene = pd.DataFrame({
        "v1_records": v1.source_file.value_counts(), "v3_records": v3.source_file.value_counts(),
        "v1_damaged": v1.groupby("source_file").damaged.sum(), "v3_damaged": v3.groupby("source_file").damaged.sum()})
    return t, by_scene


# ---------------------------------------------------------------- 2. mapping (copy of map_product)
def base_in(src):
    import glob
    parts = sorted(glob.glob(os.path.join(gp.BASE_CACHE, "region=*", "*.parquet")))
    if not parts:
        raise FileNotFoundError(f"Overture base cache missing at {gp.BASE_CACHE}; see exploratory/paper/README.md")
    win = gpd.GeoSeries([src.union_all().envelope.buffer(SNAP_M * 2)], crs=gp.METRIC_CRS).to_crs(4326).iloc[0]
    frames = []
    for p in parts:
        g = gpd.read_parquet(p, columns=["id", "geometry"])
        g = g.set_crs(4326) if g.crs is None else g.to_crs(4326)
        g = g[g.geometry.intersects(win)]
        if len(g):
            frames.append(g)
    b = gp.to_metric(gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=4326).drop_duplicates("id"))
    b["b_area"] = b.geometry.area
    return b


def map_to_base(delivered) -> set:
    """Damaged delivered footprints -> base ids: highest IoU, else nearest within SNAP_M."""
    # silver stores Microsoft in 4326; route through it so the geometry matches what the paper mapped
    src = gp.to_metric(delivered.to_crs(4326)).reset_index(drop=True).reset_index(names="sid")
    src["s_area"] = src.geometry.area
    base = base_in(src)
    inter = gpd.overlay(src[["sid", "s_area", "geometry"]], base[["id", "b_area", "geometry"]],
                        how="intersection", keep_geom_type=False)
    inter["ov"] = inter.geometry.area
    inter = inter[inter.ov > 0]
    inter["iou"] = inter.ov / (inter.s_area + inter.b_area - inter.ov)
    best = inter.sort_values(["sid", "iou", "id"], ascending=[True, False, True]).groupby("sid").head(1)[["sid", "id"]]
    rest = src[~src.sid.isin(best.sid)]
    if len(rest):
        j = gpd.sjoin_nearest(rest[["sid", "geometry"]], base[["id", "geometry"]], max_distance=SNAP_M,
                              how="left", distance_col="d")
        j = j[~j.index.duplicated()]
        best = pd.concat([best, j[j.id.notna()][["sid", "id"]]], ignore_index=True)
    return set(best.id)


# ---------------------------------------------------------------- 3/4. scoring through the paper's scorecards
def with_ms(ids: set):
    b = pl.buildings().copy()
    b["ms_dmg"] = b["id"].isin(ids).astype("int64")
    b["votes"] = b[list(pl.PRODUCTS.values())].sum(axis=1)
    return b


def run_scorecards(ids: set, fns) -> pd.DataFrame:
    orig = pl.buildings
    b = with_ms(ids)
    pl.buildings = lambda: b            # scorecards reads buildings through paperlib
    try:
        out = pd.DataFrame(sum((f() for f in fns), []))
    finally:
        pl.buildings = orig
    return out


def gate_v1(v1_ids: set, v1_scores: pd.DataFrame):
    paper_ids = set(pd.read_csv(os.path.join(PAPER, "lib", "ms_1to1_ids.csv")).id)
    if v1_ids != paper_ids:
        raise SystemExit(f"v1 mapping differs from lib/ms_1to1_ids.csv: {len(v1_ids ^ paper_ids)} ids")
    res = pd.read_csv(os.path.join(PAPER, "results.csv"))
    k = ["region", "lens", "radius", "predictor", "metric"]
    mine = v1_scores[v1_scores.predictor == "MS"].copy()
    mine["radius"] = mine.radius.astype("float")
    res["radius"] = pd.to_numeric(res.radius, errors="coerce")
    j = mine.merge(res[k + ["value"]], on=k, how="left", suffixes=("", "_paper"))
    j = j[j.lens.isin(["points"]) & j.metric.isin(["P", "R", "F1", "n_flags"])]
    if j.value_paper.isna().any():
        raise SystemExit(f"{int(j.value_paper.isna().sum())} v1 rows have no results.csv counterpart")
    bad = j[(j.value.astype(float) - j.value_paper.astype(float)).abs() > 1e-9]
    if len(bad):
        raise SystemExit("v1 scores differ from results.csv:\n" + bad.to_string())
    print(f"gate passed: {len(v1_ids):,} base ids = lib/ms_1to1_ids.csv; {len(j)} score rows = results.csv")


def side_by_side(s1, s3, region, lens="points", radius=10, metrics=("n_flags", "P", "R", "F1")):
    def pick(s):
        x = s[(s.region == region) & (s.lens == lens) & (s.radius == radius) & (s.predictor == "MS")]
        return x.set_index("metric").value.reindex(list(metrics))
    return pd.DataFrame({"v1": pick(s1), "v3": pick(s3)})


def subgroup_precision(v, region, ref, label):
    """Precision of subsets of the damaged footprints, each mapped to the base on its own."""
    b = pl.buildings()
    inb_ids = set(b.loc[pl.in_region(b, region), "id"])
    dmg = v[v.damaged == 1]
    groups = {"Catia La Mar Vantor scene": dmg.source_file == RETHRESHOLD_SCENE,
              "other scenes": dmg.source_file != RETHRESHOLD_SCENE,
              "seen in 1 scene": dmg.num_observations == 1,
              "seen in 2+ scenes": dmg.num_observations >= 2}
    rows = []
    for g, mask in groups.items():
        ids = map_to_base(dmg[mask]) & inb_ids
        fl = b[b.id.isin(ids)]
        rows.append(dict(version=label, group=g, n_flags=len(fl),
                         P=round(float(gp.within_r(fl, ref, 10).mean()), 3) if len(fl) else np.nan))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v3", required=True, help="path to ALL_AOIS_building_predictions_deduplicated_v3.gpkg")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    pd.set_option("display.width", 200)

    v1, v3 = load_versions(a.v3)
    t, by_scene = decompose(v1, v3)
    print(t.to_string(index=False)); print(by_scene.to_string())

    ids1, ids3 = map_to_base(v1[v1.damaged == 1]), map_to_base(v3[v3.damaged == 1])
    print(f"base ids: v1 {len(ids1):,}  v3 {len(ids3):,}  kept {len(ids1 & ids3):,}  "
          f"dropped {len(ids1 - ids3):,}  new {len(ids3 - ids1):,}")

    fns = [sc.core_points, sc.as_delivered, sc.west_strip]
    s1, s3 = run_scorecards(ids1, fns), run_scorecards(ids3, fns)
    gate_v1(ids1, s1)
    s1.assign(version="v1").pipe(lambda d: pd.concat([d, s3.assign(version="v3")])).to_csv(os.path.join(OUT, "scores.csv"), index=False)

    for reg in ("core", "asd"):
        print(f"\n== {reg}, points frame, 10 m"); print(side_by_side(s1, s3, reg).to_string())
    print("\n== core, other radii")
    for r in (20, 30):
        print(r, side_by_side(s1, s3, "core", radius=r).T.to_string())
    print("\n== best agreement rule in the core (context only; the brief keeps v1)")
    for k in range(1, 7):
        print(f"{k}-of-6", side_by_side(s1.assign(predictor=s1.predictor.replace({f'{k}-of-6': 'MS', 'MS': '_'})),
                                        s3.assign(predictor=s3.predictor.replace({f'{k}-of-6': 'MS', 'MS': '_'})),
                                        "core").T.to_string(header=False))
    print("\n== per CEMS area (as delivered)")
    aois = sorted(set(s1.region) - {"core", "asd", "strip-west", "strip-east"})
    print(pd.concat({r: side_by_side(s1, s3, r, metrics=("n_flags", "P", "R")).stack() for r in aois}, axis=1).T.to_string())
    print("\n== Caraballeda strip at Microsoft's scene boundary")
    for side in ("strip-west", "strip-east"):
        print(side, side_by_side(s1, s3, side, metrics=("n_flags", "flag_share", "P")).T.to_string())

    ext = gp.to_metric(gp.cems_extent().query("is_latest")).geometry.make_valid().union_all()
    region = ext.intersection(pl.product_aois()["MS"])
    ref = pl.reference("floor"); ref = ref[ref.geometry.within(region)]
    sub = pd.DataFrame(subgroup_precision(v1, region, ref, "v1") + subgroup_precision(v3, region, ref, "v3"))
    print("\n== by primary scene and by number of observing scenes (as delivered, 10 m precision)")
    print(sub.pivot(index="group", columns="version", values=["n_flags", "P"]).to_string())
    # where the re-thresholded scene sits relative to the strip split
    lon = v3[v3.source_file == RETHRESHOLD_SCENE].to_crs(4326).geometry.representative_point().x
    print(f"\nCatia La Mar Vantor scene longitude range: {lon.min():.3f} to {lon.max():.3f} (strip split at {sc.SPLIT_LON})")


if __name__ == "__main__":
    main()
