"""Serving queries for the viewer's API.

All reads go through DuckDB over blob (cloud-optimized). The FastAPI layer
(api/) turns these into GeoJSON/JSON for the deck.gl + MapLibre front end.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from gie import db
from gie.config import load_settings


def _gold(settings, source: str, adm0: str) -> str:
    return settings.az_path("gold", f"source={source}", f"adm0={adm0}", "damage_facts.parquet")


def load_h3_damage(
    source: str = "microsoft", adm0: str = "VE", stage: str = "dev"
) -> pd.DataFrame:
    """Per-H3-cell damage metrics (wide), for the hexagon layer."""
    settings = load_settings(stage)  # type: ignore[arg-type]
    con = db.connect()
    gold = _gold(settings, source, adm0)
    return con.execute(
        f"""
        SELECT unit_id AS h3,
            max(value) FILTER (WHERE metric='buildings_total')  AS buildings_total,
            max(value) FILTER (WHERE metric='buildings_damaged') AS buildings_damaged,
            max(value) FILTER (WHERE metric='damaged_fraction')  AS damaged_fraction,
            max(value) FILTER (WHERE metric='damage_pct_mean')   AS damage_pct_mean
        FROM read_parquet('{gold}') WHERE unit_type='h3' GROUP BY unit_id
        """
    ).df()


def load_admin_damage(
    level: int = 3, source: str = "microsoft", adm0: str = "VE", stage: str = "dev"
) -> gpd.GeoDataFrame:
    """Admin units at ``level`` joined to damage facts.

    For adm3 we return every parroquia within the affected municipalities
    (siblings render as 'no data' for context); for adm1/adm2, only affected
    units. Result carries geometry + metrics for a choropleth.
    """
    settings = load_settings(stage)  # type: ignore[arg-type]
    con = db.connect()
    gold = _gold(settings, source, adm0)
    adm = settings.az_path("bronze", "source=codab", f"adm0={adm0}", f"adm{level}.parquet")
    idcol, namecol = f"adm{level}_id", f"adm{level}_name"

    if level >= 3:
        # parroquias within affected municipalities (context around the data)
        where = (
            f"a.adm2_id IN (SELECT DISTINCT unit_id "
            f"FROM read_parquet('{gold}') WHERE unit_type='adm2')"
        )
    else:
        where = "f.buildings_total IS NOT NULL"  # affected units only

    df = con.execute(
        f"""
        WITH facts AS (
            SELECT unit_id AS {idcol},
                max(value) FILTER (WHERE metric='buildings_total')   AS buildings_total,
                max(value) FILTER (WHERE metric='buildings_damaged') AS buildings_damaged,
                max(value) FILTER (WHERE metric='damaged_fraction')  AS damaged_fraction
            FROM read_parquet('{gold}') WHERE unit_type='adm{level}' GROUP BY unit_id
        )
        SELECT a.{idcol} AS unit_id, a.{namecol} AS unit_name, ST_AsWKB(a.geometry) AS wkb,
               f.buildings_total, f.buildings_damaged, f.damaged_fraction
        FROM read_parquet('{adm}') a
        LEFT JOIN facts f USING ({idcol})
        WHERE {where}
        """
    ).df()
    geom = gpd.GeoSeries.from_wkb(df.pop("wkb").map(bytes), crs="EPSG:4326")
    return gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")


def load_footprints(
    source: str = "microsoft", adm0: str = "VE", stage: str = "dev"
) -> gpd.GeoDataFrame:
    """Raw building footprints with damage attributes, for the footprint layer."""
    settings = load_settings(stage)  # type: ignore[arg-type]
    con = db.connect()
    silver = settings.az_path("silver", f"source={source}", f"adm0={adm0}", "footprints.parquet")
    df = con.execute(
        f"""
        SELECT damaged, damage_pct_10m, ST_AsWKB(geometry) AS wkb
        FROM read_parquet('{silver}')
        """
    ).df()
    geom = gpd.GeoSeries.from_wkb(df.pop("wkb").map(bytes), crs="EPSG:4326")
    return gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")


# --- common-model (gold/model=common) readers ------------------------------
_COMMON_PIVOT = """
    max(value) FILTER (WHERE metric='exposed_buildings')     AS exposed_buildings,
    max(value) FILTER (WHERE metric='analysed_buildings')    AS analysed_buildings,
    max(value) FILTER (WHERE metric='coverage_fraction')     AS coverage_fraction,
    max(value) FILTER (WHERE metric='damaged_detected')      AS damaged_detected,
    max(value) FILTER (WHERE metric='damaged_extrapolated')  AS damaged_extrapolated,
    max(value) FILTER (WHERE metric='analysed_area_km2')     AS analysed_area_km2,
    max(value) FILTER (WHERE metric='unit_area_km2')         AS unit_area_km2,
    max(value) FILTER (WHERE metric='area_coverage_fraction') AS area_coverage_fraction
"""


def list_sources(adm0: str = "VE", stage: str = "dev") -> list[str]:
    """Distinct damage sources present in the common-model gold."""
    settings = load_settings(stage)  # type: ignore[arg-type]
    con = db.connect()
    gold = settings.az_path("gold", "model=common", f"adm0={adm0}", "facts.parquet")
    rows = con.execute(
        f"SELECT DISTINCT source FROM read_parquet('{gold}') ORDER BY source"
    ).fetchall()
    return [r[0] for r in rows]


def load_common_h3(source: str, adm0: str = "VE", stage: str = "dev") -> pd.DataFrame:
    """Per-H3-cell common-model metrics for one source."""
    settings = load_settings(stage)  # type: ignore[arg-type]
    con = db.connect()
    gold = settings.az_path("gold", "model=common", f"adm0={adm0}", "facts.parquet")
    return con.execute(
        f"SELECT unit_id AS h3, {_COMMON_PIVOT} FROM read_parquet('{gold}') "
        f"WHERE unit_type='h3' AND source='{source}' GROUP BY unit_id"
    ).df()


def load_common_admin(
    level: int, source: str, adm0: str = "VE", stage: str = "dev"
) -> gpd.GeoDataFrame:
    """Admin units (with geometry) joined to one source's common-model metrics."""
    settings = load_settings(stage)  # type: ignore[arg-type]
    con = db.connect()
    gold = settings.az_path("gold", "model=common", f"adm0={adm0}", "facts.parquet")
    adm = settings.az_path("bronze", "source=codab", f"adm0={adm0}", f"adm{level}.parquet")
    idcol = f"adm{level}_id"
    df = con.execute(
        f"""
        WITH facts AS (
            SELECT unit_id AS {idcol}, {_COMMON_PIVOT}
            FROM read_parquet('{gold}')
            WHERE unit_type='adm{level}' AND source='{source}' GROUP BY unit_id
        )
        SELECT a.{idcol} AS unit_id, a.adm{level}_name AS unit_name,
               ST_AsWKB(a.geometry) AS wkb, f.* EXCLUDE ({idcol})
        FROM read_parquet('{adm}') a JOIN facts f USING ({idcol})
        """
    ).df()
    geom = gpd.GeoSeries.from_wkb(df.pop("wkb").map(bytes), crs="EPSG:4326")
    return gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")


def load_export(level: int, adm0: str = "VE", stage: str = "dev") -> pd.DataFrame:
    """Tidy per-admin-unit, per-source damage table for spreadsheet export.

    One row per (admin unit x source): building counts, damage fraction (damaged
    / analysed valid-area buildings), and areal coverage. Full COD name hierarchy
    for context. Sorted so a unit's sources sit on adjacent rows for comparison.
    """
    settings = load_settings(stage)  # type: ignore[arg-type]
    con = db.connect()
    gold = settings.az_path("gold", "model=common", f"adm0={adm0}", "facts.parquet")
    adm = settings.az_path("bronze", "source=codab", f"adm0={adm0}", f"adm{level}.parquet")
    names = ", ".join(f"a.adm{i}_name" for i in range(1, level + 1))
    return con.execute(
        f"""
        WITH f AS (
            SELECT unit_id, source,
                max(value) FILTER (WHERE metric='exposed_buildings')      AS total_buildings,
                max(value) FILTER (WHERE metric='analysed_buildings')     AS analysed_buildings,
                max(value) FILTER (WHERE metric='damaged_detected')       AS damaged,
                max(value) FILTER (WHERE metric='damaged_extrapolated')   AS damaged_est_full_unit,
                max(value) FILTER (WHERE metric='analysed_area_km2')      AS analysed_area_km2,
                max(value) FILTER (WHERE metric='unit_area_km2')          AS unit_area_km2,
                max(value) FILTER (WHERE metric='area_coverage_fraction') AS area_coverage_fraction
            FROM read_parquet('{gold}') WHERE unit_type='adm{level}' GROUP BY unit_id, source
        )
        SELECT {names}, f.unit_id, f.source,
               f.total_buildings, f.analysed_buildings, f.damaged,
               f.damaged / nullif(f.analysed_buildings, 0) AS damage_fraction,
               f.damaged_est_full_unit,
               f.analysed_area_km2, f.unit_area_km2, f.area_coverage_fraction
        FROM f JOIN read_parquet('{adm}') a ON a.adm{level}_id = f.unit_id
        ORDER BY {names}, f.source
        """
    ).df()


def load_buildings(source: str, adm0: str = "VE", stage: str = "dev") -> pd.DataFrame:
    """Overture base buildings (as points) the source assessed, with a damaged flag.

    Geometry stays in the Overture silver; we join the persisted per-building
    flags by id and return only buildings inside the source's coverage extent.
    """
    settings = load_settings(stage)  # type: ignore[arg-type]
    con = db.connect()
    base = settings.az_path(
        "silver", "source=overture", f"adm0={adm0}", "region=*", "*.parquet"
    )
    flags = settings.az_path("gold", "model=common", f"adm0={adm0}", "building_flags.parquet")
    dmg = "ms_dmg" if source == "microsoft" else "cems_dmg"
    seen = "ms_analysed" if source == "microsoft" else "cems_analysed"
    return con.execute(
        f"""
        SELECT round(ST_X(ST_Centroid(b.geometry)), 6) AS lon,
               round(ST_Y(ST_Centroid(b.geometry)), 6) AS lat,
               f.{dmg}::INT AS damaged
        FROM read_parquet('{base}', hive_partitioning=true) b
        JOIN read_parquet('{flags}') f USING (id)
        WHERE f.{seen}
        """
    ).df()


def load_source_extent(source: str, adm0: str = "VE", stage: str = "dev") -> gpd.GeoDataFrame:
    """Each source's analysis extent, one outline per AOI, as a labelling layer.

    Microsoft -> its valid-area masks (already clean per-AOI polygons); CEMS ->
    convex hull of each analysed-extent AOI. Tells you at a glance which region
    each source covers and where they overlap.
    """
    settings = load_settings(stage)  # type: ignore[arg-type]
    con = db.connect()
    src = "microsoft" if source == "microsoft" else "copernicus_ems"
    ext = settings.az_path("silver", f"source={src}", f"adm0={adm0}", "analysed_extent.parquet")
    if source == "microsoft":
        sql = f"SELECT ST_AsWKB(geometry) AS wkb FROM read_parquet('{ext}')"
    else:
        # CEMS analysed extent is fragmented (imagery minus cloud); hull per AOI
        sql = (
            f"SELECT ST_AsWKB(ST_ConvexHull(ST_Union_Agg(geometry))) AS wkb "
            f"FROM read_parquet('{ext}') GROUP BY src_zip"
        )
    df = con.execute(sql).df()
    geom = gpd.GeoSeries.from_wkb(df.pop("wkb").map(bytes), crs="EPSG:4326")
    return gpd.GeoDataFrame({"source": [source] * len(geom)}, geometry=geom, crs="EPSG:4326")


def load_native(source: str, adm0: str = "VE", stage: str = "dev") -> gpd.GeoDataFrame:
    """Each source's own damage geometry (the 'native data' view).

    Microsoft -> footprints with a binary damaged flag; CEMS -> damage-grade
    polygons with the EMS grade. Distinct geometries that overlay cleanly and
    show what each source actually mapped, vs the Overture-base view.
    """
    settings = load_settings(stage)  # type: ignore[arg-type]
    con = db.connect()
    if source == "microsoft":
        path = settings.az_path("silver", "source=microsoft", f"adm0={adm0}", "footprints.parquet")
        cols = "damaged"
    else:
        path = settings.az_path(
            "silver", "source=copernicus_ems", f"adm0={adm0}", "builtup_damage.parquet"
        )
        cols = "ems_grade, damage_class"
    df = con.execute(
        f"SELECT {cols}, ST_AsWKB(geometry) AS wkb FROM read_parquet('{path}')"
    ).df()
    geom = gpd.GeoSeries.from_wkb(df.pop("wkb").map(bytes), crs="EPSG:4326")
    return gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")


def load_coverage_detail(adm0: str = "VE", stage: str = "dev") -> gpd.GeoDataFrame:
    """CEMS Area-of-Interest + Not-Analysed (cloud) shapes, for the native view.

    Shows what the assessment looked at (AOI) and the holes within it that
    couldn't be assessed (cloud / no imagery) — so coverage gaps are visible.
    """
    settings = load_settings(stage)  # type: ignore[arg-type]
    con = db.connect()
    path = settings.az_path(
        "silver", "source=copernicus_ems", f"adm0={adm0}", "coverage_detail.parquet"
    )
    df = con.execute(
        f"SELECT kind, ST_AsWKB(geometry) AS wkb FROM read_parquet('{path}')"
    ).df()
    geom = gpd.GeoSeries.from_wkb(df.pop("wkb").map(bytes), crs="EPSG:4326")
    return gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")


def load_agreement(adm0: str = "VE", stage: str = "dev") -> pd.DataFrame:
    """Per-building source-agreement category (MS vs CEMS) for the agreement map.

    Where BOTH sources assessed a building (the overlap): both / ms_only /
    cems_only / agree_none. Where only one looked: ms_area / cems_area. This is
    the spatial Venn — it shows where the sources agree and, crucially, where
    they disagree.
    """
    settings = load_settings(stage)  # type: ignore[arg-type]
    con = db.connect()
    base = settings.az_path("silver", "source=overture", f"adm0={adm0}", "region=*", "*.parquet")
    flags = settings.az_path("gold", "model=common", f"adm0={adm0}", "building_flags.parquet")
    return con.execute(
        f"""
        WITH b AS (
            SELECT id, geometry FROM read_parquet('{base}', hive_partitioning=true)
            QUALIFY row_number() OVER (PARTITION BY id) = 1
        )
        SELECT round(ST_X(ST_Centroid(b.geometry)), 6) AS lon,
               round(ST_Y(ST_Centroid(b.geometry)), 6) AS lat,
               CASE
                 WHEN f.ms_analysed AND f.cems_analysed THEN
                   CASE WHEN f.ms_dmg AND f.cems_dmg THEN 'both'
                        WHEN f.ms_dmg THEN 'ms_only'
                        WHEN f.cems_dmg THEN 'cems_only'
                        ELSE 'agree_none' END
                 WHEN f.ms_analysed THEN 'ms_area'
                 ELSE 'cems_area' END AS agreement
        FROM b JOIN read_parquet('{flags}') f USING (id)
        WHERE f.ms_analysed OR f.cems_analysed
        """
    ).df()


def damage_colors(
    fractions, *, na: tuple[int, int, int, int] = (200, 200, 200, 40)
) -> np.ndarray:
    """Map a damaged-fraction series (0..1, NaN allowed) to an RGBA uint8 array."""
    f = np.asarray(fractions, dtype="float64")
    out = np.empty((len(f), 4), dtype="uint8")
    valid = ~np.isnan(f)
    fc = np.clip(f[valid], 0.0, 1.0)
    out[valid, 0] = 240
    out[valid, 1] = (220 * (1 - fc)).astype("uint8")
    out[valid, 2] = (40 * (1 - fc)).astype("uint8")
    out[valid, 3] = 200
    out[~valid] = na
    return out
