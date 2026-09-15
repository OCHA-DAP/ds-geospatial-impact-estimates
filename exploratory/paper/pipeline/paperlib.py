"""The paper's shared definitions, in one place (ADR-0032).

Every quantity the brief reports is computed through these functions, so a convention lives
here once, with the ADR that fixed it:

  * frame          gie_paper.buildings()  — footprint geometry on the shared base, Microsoft
                   mapped 1:1 (ADR-0030); location for cells/regions = representative point
  * matching       within_r / match_rate  — polygon distance, containment counts (ADR-0030)
  * crowd credit   measured: a flag is credited only if the crowd reviewed its cell and judged
                   it damaged; unreviewed flags earn nothing (ADR-0031)
  * regions        core = CEMS latest extent ∩ the six products' analysed extents

Data access is delegated to lib/gie_paper.py (loaders, pins, the base cache); this
module adds the definitions the 40 frozen scripts used to re-implement individually.
"""
from __future__ import annotations

import gzip
import json
import os
import sys
from functools import lru_cache

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from shapely.geometry import Polygon
from shapely.ops import unary_union

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import gie_paper as gp  # noqa: E402

METRIC_CRS = gp.METRIC_CRS
PRODUCTS = {"MS": "ms_dmg", "IMPACT": "sar_dmg", "OSU": "osu_dmg", "UH": "uh_dmg", "LIST": "list_dmg", "UNEP": "debris_dmg"}
PAIRS = [("IMPACT", "OSU"), ("MS", "UH"), ("MS", "LIST"), ("LIST", "UH"), ("UNEP", "OSU"), ("MS", "UNEP")]
GRADES = {"floor": (2, 3), "grade": (1, 2, 3), "destroyed": (3,)}   # CEMS damage_class sets
RADII = (10, 20, 30)          # matching radii reported; 10 m is the paper's radius
FIELD_R = 20                  # ChatMap GPS tolerance
CROWD_MIN_VOTES = 4


# ---------------------------------------------------------------- geometry helpers
def location(gdf: gpd.GeoDataFrame) -> gpd.GeoSeries:
    """A building's location for cell assignment and region membership (ADR-0030)."""
    return gdf.geometry.representative_point()


def in_region(gdf: gpd.GeoDataFrame, region) -> np.ndarray:
    return location(gdf).within(region).to_numpy()


def cells(gdf: gpd.GeoDataFrame, res: int) -> np.ndarray:
    ll = location(gdf).to_crs(4326)
    return np.array([h3.latlng_to_cell(p.y, p.x, res) for p in ll])


# ---------------------------------------------------------------- regions
@lru_cache(maxsize=None)
def uh_aoi():
    """UH delivered no extent: res-9 cells holding its footprints, dilated by one ring."""
    g = gp._read_pq("silver", "source=uh", "adm0=VE", "footprints.parquet")
    cs = {h3.latlng_to_cell(p.y, p.x, 9) for p in g.geometry.representative_point()}
    dil = set()
    for c in cs:
        dil.update(h3.grid_disk(c, 1))
    polys = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in dil]
    return gp.dissolve_union(gpd.GeoDataFrame(geometry=[unary_union(polys)], crs=4326))


@lru_cache(maxsize=None)
def product_aois() -> dict:
    """Each product's analysed extent as one metric (multi)polygon. UNEP stated none."""
    return {
        "MS": gp.dissolve_union(gp.microsoft_aoi()),
        "IMPACT": gp.dissolve_union(gp.impact_v2_aoi()),
        "OSU": gp.dissolve_union(gp.osu_aoi()),
        "UH": uh_aoi(),
        "LIST": gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE", "analysed_extent.parquet")),
    }


@lru_cache(maxsize=None)
def cems_extent_latest():
    return gp.to_metric(gp.cems_extent().query("is_latest")).geometry.make_valid().union_all()


@lru_cache(maxsize=None)
def core_region():
    """Where all six products and the reference overlap: the paper's comparison region."""
    region = cems_extent_latest()
    for a in product_aois().values():
        region = region.intersection(a)
    return region


# ---------------------------------------------------------------- data
@lru_cache(maxsize=None)
def buildings() -> gpd.GeoDataFrame:
    """Shared-base buildings with the six flag columns (0/1) and a `votes` column."""
    b = gp.buildings(columns=list(PRODUCTS.values()))
    for c in PRODUCTS.values():
        b[c] = (b[c].to_numpy(dtype="float64", na_value=0.0) == 1).astype("int64")
    b["votes"] = b[list(PRODUCTS.values())].sum(axis=1)
    return b


@lru_cache(maxsize=None)
def reference(grade: str = "floor") -> gpd.GeoDataFrame:
    """CEMS latest per-building damage points (metric) for a grade set from GRADES."""
    c = gp.to_metric(gp.cems_points())
    return c[c.damage_class.isin(GRADES[grade])][["geometry"]].reset_index(drop=True)


@lru_cache(maxsize=None)
def field_points() -> gpd.GeoDataFrame:
    """ChatMap field-validated damage points (metric)."""
    import ocha_stratus as stratus
    raw = stratus.load_blob_data(gp.S.blob_path("bronze", "source=mapswipe", "adm0=VE", "hdx",
                                                "chatmap_field_validated_damage_points.geojson", event=None),
                                 stage="dev", container_name=gp.S.container)
    return gpd.GeoDataFrame.from_features(json.loads(raw)["features"], crs=4326).to_crs(METRIC_CRS)


@lru_cache(maxsize=None)
def crowd_tasks() -> pd.DataFrame:
    """Frozen MapSwipe task cells (>= CROWD_MIN_VOTES votes) with the majority verdict
    (0 no damage, 1 damaged, 2 not sure), indexed by h3 id. Round-2 re-votes excluded."""
    import ocha_stratus as stratus
    cc = stratus.get_container_client(stage="dev", container_name=gp.S.container)
    pref = gp.S.blob_path("bronze", "source=mapswipe", "adm0=VE", event=None)
    frames = []
    for b in cc.list_blobs(name_starts_with=pref):
        if not gp.mapswipe_is_frozen(b.name):
            continue
        if "agg_results_by_task" in b.name and b.name.endswith(".geojson.gz"):
            feats = json.loads(gzip.decompress(cc.download_blob(b.name).readall()))["features"]
            rows = [f["properties"] for f in feats if f["properties"].get("h3")]
            if rows:
                frames.append(pd.DataFrame(rows))
    t = pd.concat(frames, ignore_index=True)
    t = t[t.total_count >= CROWD_MIN_VOTES].copy()
    t["majority"] = t[["0_share", "1_share", "2_share"]].to_numpy().argmax(axis=1)
    return t.drop_duplicates(subset="h3", keep="first").set_index("h3")[["majority", "res"]]


def crowd_verdicts(gdf: gpd.GeoDataFrame) -> np.ndarray:
    """Majority verdict of the crowd cell (res 11, else 12) holding each building's location;
    NaN where the crowd never voted that cell. ADR-0031: NaN is 'no credit', not 'unknown rate'."""
    tasks = crowd_tasks()
    out = np.full(len(gdf), np.nan)
    ll = location(gdf).to_crs(4326)
    for i, p in enumerate(ll):
        for res in (11, 12):
            c = h3.latlng_to_cell(p.y, p.x, res)
            if c in tasks.index:
                out[i] = float(tasks.loc[c, "majority"])
                break
    return out


# ---------------------------------------------------------------- predictors
def predictors(b: gpd.GeoDataFrame) -> dict:
    """Named boolean masks over `b`: the six products, six pairs, six k-of-6 rules."""
    out = {p: b[c].to_numpy() == 1 for p, c in PRODUCTS.items()}
    for a, c in PAIRS:
        out[f"{a}∧{c}"] = out[a] & out[c]
    for k in range(1, 7):
        out[f"{k}-of-6"] = b["votes"].to_numpy() >= k
    return out


# ---------------------------------------------------------------- scoring
def score(flagged: gpd.GeoDataFrame, ref: gpd.GeoDataFrame, r: float) -> dict:
    """Dual-anchored precision/recall at radius r (polygon distance, ADR-0030).
    P = share of flagged buildings with a reference point within r;
    R = share of reference points with a flagged building within r."""
    nr, dr = gp.match_rate(ref, flagged, r)
    np_, dp = gp.match_rate(flagged, ref, r)
    P = np_ / dp if dp else np.nan
    R = nr / dr if dr else np.nan
    F1 = 2 * P * R / (P + R) if (P or 0) + (R or 0) > 0 else 0.0
    return dict(P=P, R=R, F1=F1, n_flags=dp, n_ref=dr, tp=np_)


def crowd_credit(flagged: gpd.GeoDataFrame, ref: gpd.GeoDataFrame, r: float) -> dict:
    """Measured crowd adjustment (ADR-0031): unmatched flags whose cell the crowd reviewed and
    judged damaged are added to the numerator; unreviewed flags earn nothing."""
    hit = gp.within_r(flagged, ref, r)
    un = flagged[~hit]
    v = crowd_verdicts(un) if len(un) else np.array([])
    n_conf = int((v == 1).sum())
    reviewed = int((~np.isnan(v)).sum()) if len(v) else 0
    n = len(flagged)
    return dict(P_crowd=(hit.sum() + n_conf) / n if n else np.nan,
                crowd_cov=reviewed / len(un) if len(un) else np.nan,
                fp_crowd_damaged=n_conf / reviewed if reviewed else np.nan)
