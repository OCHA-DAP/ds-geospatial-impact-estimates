"""Exploratory 0001 — the duplicate footprints in Microsoft's merged VE damage set:
are they from Microsoft or from Overture, and how many are there?

Findings: findings.md (same folder). Feeds docs/decisions/0010.

Reads the immutable bronze snapshot of Microsoft's merged file and characterises the
duplication end to end. Verdict (see findings.md): they are Microsoft cross-scene
merge MISSES — the same building detected in two overlapping satellite scenes, whose
per-scene footprints overlapped too little to be merged. Not an Overture artifact.

  1. id check              — is any building id duplicated?
  2. orig_id co-location   — is orig_id a building id, or a colliding tile-local id?
  3. exact-geometry dups
  4. spatial near-dup clusters + the true unique / damaged counts
  5. cross-scene verification — source_file = scenes; mutual-NN; one-per-scene
  6. Microsoft-metadata cross-check — num_observations / sources

Run (needs the dev-lake env: GIE_BLOB_ACCOUNT_PREFIX + DSCI_AZ_BLOB_DEV_SAS):
  uv run --group etl --with scipy python \
    exploratory/0001-microsoft-overture-duplicates/analysis.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # exploratory/<entry>/ -> repo root
sys.path.insert(0, str(ROOT / "src"))

import geopandas as gpd
import numpy as np
import ocha_stratus as stratus
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from gie.config import load_settings

NAME = "ALL_AOIS_building_predictions_deduplicated.gpkg"
REPORTED_ANALYZED, REPORTED_DAMAGED = 72_162, 8_410  # Microsoft's published headline stats


def load_bronze() -> gpd.GeoDataFrame:
    s = load_settings("dev")
    bp = s.blob_path("bronze", "source=microsoft", "adm0=VE", "merged", NAME)
    data = stratus.load_blob_data(bp, stage="dev", container_name=s.container)
    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tf:
        tf.write(data)
        tmp = tf.name
    gdf = gpd.read_file(tmp).to_crs(32619).reset_index(drop=True)  # UTM 19N for metric ops
    os.unlink(tmp)
    return gdf


def dup_edges(xy, area, sf, cdist_max=3.0, aratio_min=0.7):
    """Same-building candidate pairs: close centroid, similar area, DIFFERENT scene.
    Overlap-independent on purpose — Microsoft's per-scene jitter drives IoU down, so
    proximity + size is a more faithful 'same building' signal than overlap."""
    cand = cKDTree(xy).query_pairs(r=8.0, output_type="ndarray")
    i, j = cand[:, 0], cand[:, 1]
    cd = np.hypot(xy[i, 0] - xy[j, 0], xy[i, 1] - xy[j, 1])
    ar = np.minimum(area[i], area[j]) / np.maximum(area[i], area[j])
    keep = (cd <= cdist_max) & (ar >= aratio_min) & (sf[i] != sf[j])
    return cand[keep]


def main() -> None:
    g = load_bronze()
    n = len(g)
    area = g.geometry.area.values
    xy = np.c_[g.geometry.centroid.x.values, g.geometry.centroid.y.values]
    dmg = g["damaged"].values == 1
    sf = g["source_file"].values
    nobs = g["num_observations"].values
    print(f"rows: {n:,}   (Microsoft reports {REPORTED_ANALYZED:,} analysed, "
          f"{REPORTED_DAMAGED:,} damaged)")

    # 1) id check -------------------------------------------------------------
    print("\n[1] id duplication")
    for c in ("id", "orig_id"):
        share = int(g[c].duplicated(keep=False).sum())
        print(f"    {c}: {g[c].nunique():,} unique / {n:,} -> {share:,} rows share a value")

    # 2) is orig_id a building id, or a colliding tile-local id? ---------------
    orig = g["orig_id"].astype(str).values
    md = pd.DataFrame({"orig": orig, "x": xy[:, 0], "y": xy[:, 1]})
    md = md[pd.Series(orig).duplicated(keep=False).values]
    gm = md.groupby("orig")
    md = md.assign(d=np.hypot(md.x - gm.x.transform("mean"), md.y - gm.y.transform("mean")))
    spread = md.groupby("orig")["d"].max()
    print("\n[2] orig_id co-location (rows sharing an orig_id)")
    print(f"    within-orig_id centroid spread: median {spread.median():,.0f} m, "
          f"p99 {spread.quantile(0.99):,.0f} m")
    print(f"    -> orig_id is a COLLIDING tile-local id (same value on buildings km "
          f"apart), not a building identity. Dead end.")

    # 3) exact-geometry duplicates --------------------------------------------
    exact = int(g.geometry.to_wkb().duplicated(keep=False).sum())
    print(f"\n[3] exact-duplicate geometries: {exact:,} (jittered copies, never identical)")

    # 4) spatial near-dup clusters + true counts ------------------------------
    print("\n[4] spatial duplicate clusters -> true unique / damaged counts")
    for label, cdm, arm in [("tight  (<=3m, area>=0.7)", 3.0, 0.7),
                            ("looser (<=5m, area>=0.6)", 5.0, 0.6)]:
        e = dup_edges(xy, area, sf, cdm, arm)
        m = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
        ncomp, lab = connected_components(m, directed=False)
        size = np.bincount(lab, minlength=ncomp)
        dcount = np.bincount(lab, weights=dmg.astype(float), minlength=ncomp)
        uniq_dmg = int((dcount > 0).sum())
        mixed = int(((dcount > 0) & (dcount < size)).sum())
        print(f"    {label}: unique buildings {ncomp:,} "
              f"(reported {REPORTED_ANALYZED:,}, +{100*(REPORTED_ANALYZED-ncomp)/REPORTED_ANALYZED:.1f}% inflated) | "
              f"unique damaged {uniq_dmg:,} "
              f"(reported {REPORTED_DAMAGED:,}, +{100*(REPORTED_DAMAGED-uniq_dmg)/REPORTED_DAMAGED:.1f}%) | "
              f"scenes disagree on damage: {mixed:,}")

    # primary criterion for the verification sections below
    edges = dup_edges(xy, area, sf)
    m = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(n, n))
    ncomp, lab = connected_components(m, directed=False)
    size = np.bincount(lab, minlength=ncomp)
    in_cluster = size[lab] > 1

    # 5) verify the cross-scene mechanism -------------------------------------
    print("\n[5] cross-scene verification")
    print("    source_file values (= the satellite scenes):")
    for name, cnt in g["source_file"].value_counts().items():
        print(f"      {cnt:>6,}  {name}")
    _, inn = cKDTree(xy).query(xy, k=2)
    nn = inn[:, 1]
    mutual = int(sum(nn[a] == b and nn[b] == a for a, b in edges))
    print(f"    duplicate members that are MUTUAL nearest neighbours: "
          f"{mutual:,}/{len(edges):,} ({100*mutual/len(edges):.0f}%)  [same-building]")
    from collections import defaultdict
    members = defaultdict(list)
    for idx, c in enumerate(lab):
        members[c].append(idx)
    multi = [idx for idx in members.values() if len(idx) > 1]
    one_per_scene = sum(1 for idx in multi if len(idx) == len(set(sf[idx])))
    print(f"    clusters with one footprint per distinct scene: "
          f"{one_per_scene:,}/{len(multi):,} ({100*one_per_scene/len(multi):.0f}%)  [overlap dupes]")

    # 6) cross-check against Microsoft's own metadata -------------------------
    src = g["sources"].fillna("").astype(str).values
    n_scenes = np.array([len(s.split(",")) if s else 0 for s in src])
    print("\n[6] Microsoft-metadata cross-check")
    print(f"    num_observations == #scenes listed in `sources`: "
          f"{100*(nobs == n_scenes).mean():.0f}% (internally consistent)")
    print(f"    rows Microsoft MERGED across scenes (num_observations>1): "
          f"{int((nobs > 1).sum()):,}")
    print(f"    our spatial-duplicate rows with num_observations==1: "
          f"{100*(nobs[in_cluster] == 1).mean():.0f}%  [merge did NOT recognise them]")
    print(f"    overlap between 'merged' and 'duplicated' populations: "
          f"{int(((nobs > 1) & in_cluster).sum()):,} rows  [disjoint: a building is one or the other]")


if __name__ == "__main__":
    main()
