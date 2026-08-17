"""Shared readers + helpers for the paper performance analysis (RQ1-RQ4).

All reads hit immutable silver/bronze snapshots (ADR-0005). Non-destructive — never writes
to the shared blob lake. Metric ops use EPSG:32619 (UTM 19N, covers coastal VE).

Import from an RQ script:
    import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
    import gie_paper as gp
"""
from __future__ import annotations
import io, os, sys, tempfile
import geopandas as gpd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src"))
from gie.config import load_settings  # noqa: E402

S = load_settings("dev")
METRIC_CRS = 32619  # UTM 19N


def _read_pq(layer, *parts):
    import ocha_stratus as stratus
    path = S.blob_path(layer, *parts, event=None)  # frozen VE layout predates event partitions
    b = stratus.load_blob_data(path, stage="dev", container_name=S.container)
    return gpd.read_parquet(io.BytesIO(b))


def _read_gpkg(layer, *parts):
    import ocha_stratus as stratus
    path = S.blob_path(layer, *parts, event=None)  # frozen VE layout predates event partitions
    b = stratus.load_blob_data(path, stage="dev", container_name=S.container)
    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as f:
        f.write(b); tmp = f.name
    try:
        return gpd.read_file(tmp)
    finally:
        os.unlink(tmp)


# --- gold building flags, paper-pinned -----------------------------------------
OSU_PAPER_VERSION = "v0"

# MapSwipe projects ingested AFTER the 2026-07-15 freeze: round-2 re-votes of already
# frozen cells (3248 = Catia La Mar round 2, completed 2026-08-05, and a 2-option
# instrument — no "No damage" answer). Pooled loaders drop duplicate h3 ids with
# keep="first", so without this exclusion a re-run after the round-2 ingest would mix
# the two instruments on identical cells. Frozen numbers use round 1 only; round-2
# analysis lives in RQ7-mapswipe-validation's round-2 scripts, which opt in explicitly.
MAPSWIPE_POSTFREEZE = ("project=3248",)


def mapswipe_is_frozen(blob_name: str) -> bool:
    """True if a bronze MapSwipe blob belongs to the frozen (pre-2026-07-15) campaign."""
    return not any(p in blob_name for p in MAPSWIPE_POSTFREEZE)


def building_flags(columns=None):
    """Gold building_flags for PAPER use — osu_dmg/osu_class re-pinned to OSU v0.

    OSU delivered a revised v1 (69,431 flags vs v0's 58,870) on 2026-07-22, a week
    after the paper's data freeze, and the served gold/platinum moved to v1 (dashboard
    basis — do not change it). The paper scores v0, the delivery available during the
    response; silver is version-partitioned so the pin is an id-set override. The
    v0-vs-v1 comparison lives in RQ2-cems-footprint-points/scripts/rq2h_osu_v0_v1.py.
    ALL paper scripts must read gold through this helper, never directly.
    """
    import ocha_stratus as stratus
    import pandas as pd
    b = stratus.load_blob_data(S.blob_path("gold", "model=common", "adm0=VE",
                                           "building_flags.parquet", event=None),
                               stage="dev", container_name=S.container)
    cols = None if columns is None else list(dict.fromkeys([*columns, "id"]))
    df = pd.read_parquet(io.BytesIO(b), columns=cols)
    if "osu_dmg" in df.columns:
        bb = stratus.load_blob_data(
            S.blob_path("silver", "source=osu", "adm0=VE",
                        f"version={OSU_PAPER_VERSION}", "building_damage.parquet", event=None),
            stage="dev", container_name=S.container)
        ids = set(pd.read_parquet(io.BytesIO(bb), columns=["id"]).id)
        df["osu_dmg"] = df["id"].isin(ids).astype("int64")
        if "osu_class" in df.columns:
            df["osu_class"] = df["osu_dmg"] * 2
    return df


# --- CEMS ground truth ---------------------------------------------------------
def cems_all():
    return _read_pq("silver", "source=copernicus_ems", "adm0=VE", "builtup_damage.parquet")


def cems_blocks():
    """builtUpA coarse damaged-area blocks, LATEST monitoring only. damage_class 1/2/3."""
    g = cems_all()
    return g[(g.layer_type == "area") & (g.is_latest == True)].copy()  # noqa: E712


def cems_points():
    """builtUpP per-building damaged points, LATEST monitoring only (3,119 as of the
    2026-07 freeze). CEMS silver retains superseded monitoring products (is_latest=False);
    a MONIT2 Caraballeda product landed 2026-07 and doubled raw point counts — runs between
    2026-07-08 and 2026-07-15 that used unfiltered points double-counted Caraballeda
    (standing flag #13, resolved by this filter)."""
    g = cems_all()
    return g[(g.layer_type == "point") & (g.is_latest == True)].copy()  # noqa: E712


def cems_extent():
    """35 analysed-extent polygons; has product_id to match to coarse/point products."""
    return _read_pq("silver", "source=copernicus_ems", "adm0=VE", "analysed_extent.parquet")


# --- Comparison sources (damaged sets + their analysed AOIs) --------------------
def microsoft():
    g = _read_pq("silver", "source=microsoft", "adm0=VE", "footprints.parquet")
    return g[(g.damaged == 1) & (~g.superseded.astype(bool))].copy()


def microsoft_aoi():
    return _read_pq("silver", "source=microsoft", "adm0=VE", "analysed_extent.parquet")


def impact_v2():
    return _read_pq("silver", "source=impact_initiatives", "adm0=VE", "building_damage.parquet")


def impact_v2_aoi():
    return _read_pq("silver", "source=impact_initiatives", "adm0=VE", "analysed_extent.parquet")


def osu():
    """58,870 damaged Overture footprints (bronze quick-look, geometry-carrying)."""
    return _read_gpkg("bronze", "source=osu", "adm0=VE", "EMSR884_damage_20260625_v0_damaged.gpkg")


def osu_aoi():
    return _read_gpkg("bronze", "source=osu", "adm0=VE", "EMSR884_analyzed_area_20260625_v0.gpkg")


def unep():
    """UNEP/OCHA JEU building debris (96,046 GBA footprints). debris_tonnes>0 = detected damaged.
    NO analysed AOI (detected-only) -> only usable within enclosed admin units (RQ4)."""
    return _read_pq("silver", "source=unep_debris", "adm0=VE", "debris.parquet")


def codab(level=3):
    """CODAB admin boundaries. adm{level}.parquet with adm{level}_id/_name + parent ids."""
    return _read_pq("bronze", "source=codab", "adm0=VE", f"adm{level}.parquet")


def overture_window(minx, miny, maxx, maxy, region="la_guaira"):
    """All Overture base buildings (the exposure/negative stock) in a 4326 bbox.
    Reads the pipeline's local base cache (/tmp/gie_base_local) if present, else blob."""
    import glob as _glob
    import pandas as _pd
    from shapely.geometry import box as _box
    parts = _glob.glob(os.path.join("/tmp/gie_base_local", f"region={region}", "*.parquet"))
    win = _box(minx, miny, maxx, maxy)
    frames = []
    if parts:
        for p in parts:
            g = gpd.read_parquet(p)
            g = g.set_crs(4326) if g.crs is None else g.to_crs(4326)
            frames.append(g[g.geometry.intersects(win)])
    else:  # fall back to blob region parquets
        import ocha_stratus as stratus
        pref = S.blob_path("silver", "source=overture", f"adm0=VE", f"region={region}", event=None)
        for b in stratus.list_container_blobs(name_starts_with=pref, stage="dev",
                                              container_name=S.container):
            if not b.endswith(".parquet"):
                continue
            g = gpd.read_parquet(io.BytesIO(stratus.load_blob_data(b, stage="dev",
                                                                   container_name=S.container)))
            g = g.set_crs(4326) if g.crs is None else g.to_crs(4326)
            frames.append(g[g.geometry.intersects(win)])
    return gpd.GeoDataFrame(_pd.concat(frames, ignore_index=True), crs=4326)


# --- dual-anchor matcher (shared by RQ2/RQ4) -----------------------------------
def match_rate(left, right, r):
    """Fraction of `left` features with a `right` feature within r metres (containment => 0).
    Returns (n_matched, n_left). Inputs must be in metric CRS."""
    import geopandas as _gpd
    if len(left) == 0 or len(right) == 0:
        return 0, len(left)
    lft = left.reset_index(drop=True).reset_index(names="_lid")
    m = _gpd.sjoin_nearest(lft[["_lid", "geometry"]], right[["geometry"]],
                           max_distance=r, how="inner", distance_col="_d")
    return m["_lid"].nunique(), len(lft)


# --- geometry helpers ----------------------------------------------------------
def to_metric(gdf):
    return gdf.to_crs(METRIC_CRS)


def points_on_surface(gdf):
    """Representative interior point per feature (safe for polygons and points)."""
    g = gdf.copy()
    g["geometry"] = g.geometry.representative_point()
    return g


def dissolve_union(gdf):
    """Single (multi)polygon = union of all rows, in metric CRS (geometries validated first)."""
    g = to_metric(gdf)
    return g.geometry.make_valid().union_all()
