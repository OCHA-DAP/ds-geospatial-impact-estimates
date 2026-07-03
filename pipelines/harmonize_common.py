"""Common-model harmonization: project every source onto the Overture base.

The end-state of the harmonization model (ADR-0001): one shared exposure base
(Overture buildings) onto which each damage source is projected, so all sources
read in the same units. A base building is counted as damaged for a source if it
intersects that source's damage geometry:

  * Microsoft  -> intersects an MS footprint flagged damaged (binary)
  * Copernicus -> the latest CEMS layer per AOI: each damage point snapped to its
                  nearest footprint (<=20 m), or every footprint a coarse damage
                  block covers; the worst grade wins (carried as cems_class)

Coverage-aware (a source may only assess part of a unit — CEMS imagery/cloud):

  exposed_buildings    base buildings in the unit
  analysed_buildings   base buildings the source could actually assess
                       (MS: all; CEMS: inside the AOI - not-analysed extent)
  coverage_fraction    analysed / exposed  (how much of the unit was seen)
  damaged_detected     damaged base buildings in the analysed area (a floor)
  damaged_extrapolated (detected / analysed) * exposed  (observed rate applied
                       to the whole unit; NULL where coverage is zero)

Extrapolation assumes damage is spatially uniform — an estimate, not a
measurement; the viewer should gate/flag it on coverage_fraction.

Output: gold/model=common — a long fact table for cross-source comparison.

Run: uv run --group etl python pipelines/harmonize_common.py
"""

from __future__ import annotations

import os
import threading
import time

import ocha_stratus as stratus
import pandas as pd

from gie import ledger
from gie.blob import upload_parquet_staged
from gie.config import DEFAULT_H3_RESOLUTION, load_settings

METHOD = "common_overture_v1"
ADM0 = "VE"
STAGE = "dev"

# CEMS per-building damage points (builtUpP) are snapped to the nearest Overture
# footprint within this radius; 20 m matched 99.5% of points in EMSR884.
SNAP_M = 20


def _upload(frame, blob, settings) -> None:
    """Serialize to parquet and upload via staged blocks (gie.blob). The SDK
    sends blobs <= 64 MB as one long PUT that stalls on this flaky/slow uplink;
    chunking into small per-request blocks gets it through reliably."""
    upload_parquet_staged(frame, blob, settings, stage=STAGE)

# (source, damaged-flag, analysed-buildings expression). Each source only
# "analysed" within its own extent — MS within its footprint coverage, CEMS
# within imageFootprint - notAnalysed. Outside that, the source has no data
# (coverage 0), which is different from "assessed and found no damage".
SOURCES = [
    ("microsoft", "ms_dmg", "sum(ms_analysed::INT)"),
    ("copernicus_ems", "cems_dmg", "sum(cems_analysed::INT)"),
    # IMPACT Sentinel-1 SAR proxy: analysed = inside the raster extent (ADR-0008).
    ("impact_initiatives", "sar_dmg", "sum(sar_analysed::INT)"),
    # HOT fAIr damage points: detected-only. fAIr published no analysed AOI, so the
    # analysed expression is NULL — analysed_buildings, coverage_fraction and
    # damaged_extrapolated all fall out NULL, leaving only damaged_detected. When an
    # AOI lands, swap NULL for sum(hot_analysed::INT) to make it coverage-aware.
    ("hot_osm", "hot_dmg", "NULL"),
    # OSU Sentinel-1 coherence: pre-keyed to Overture (id-join); analysed =
    # inside the analyzed-area polygon (ADR-0009).
    ("osu", "osu_dmg", "sum(osu_analysed::INT)"),
    # DISHA (UN Global Pulse) zero-shot damage POINTS + AOI; snapped to the base like
    # HOT, analysed = inside the AOI. LICENCE-gated — staging preview only.
    ("disha", "disha_dmg", "sum(disha_analysed::INT)"),
]
GRAINS = [
    ("h3", "h3", None),
    ("adm0", "adm0_id", "adm0_name"),
    ("adm1", "adm1_id", "adm1_name"),
    ("adm2", "adm2_id", "adm2_name"),
    ("adm3", "adm3_id", "adm3_name"),
]
METRICS = (
    "exposed_buildings, analysed_buildings, coverage_fraction, "
    "damaged_detected, damaged_extrapolated"
)


def _fetch(blob, dst, settings, stage, tries: int = 10, timeout_s: int = 45) -> None:
    """Download one blob to dst with a per-file timeout + retry. The endpoint is
    stalling sustained transfers, so abandon a stalled fetch and retry it in a
    fresh window rather than hanging at 0% CPU forever."""
    for attempt in range(tries):
        result: dict = {}

        def _do(result=result):
            try:
                result["data"] = stratus.load_blob_data(
                    blob, stage=stage, container_name=settings.container
                )
            except Exception as e:  # noqa: BLE001
                result["err"] = e

        th = threading.Thread(target=_do, daemon=True)
        th.start()
        th.join(timeout_s)
        if "data" in result:
            with open(dst, "wb") as f:
                f.write(result["data"])
            return
        reason = "stalled" if th.is_alive() else str(result.get("err", ""))[:40]
        print(f"    {os.path.basename(dst)} retry {attempt + 1}/{tries} ({reason})", flush=True)
        time.sleep(2)
    raise RuntimeError(f"download failed after {tries} tries: {blob}")


def _local_base(settings, stage: str = STAGE) -> str:
    """Download the Overture base region parquets to local disk once (cached).

    DuckDB's azure-extension read intermittently *stalls* on the large sustained
    base scan over this endpoint, and the read has no timeout, so it hangs at 0%
    CPU forever. The Azure SDK download (stratus) is robust here, so we pull the
    base to disk and let DuckDB read local files. Other inputs are small and read
    fine straight from blob. Returns a local hive glob path."""
    prefix = settings.blob_path("silver", "source=overture", f"adm0={ADM0}")
    blobs = [
        b
        for b in stratus.list_container_blobs(
            name_starts_with=prefix, stage=stage, container_name=settings.container
        )
        if b.endswith(".parquet")
    ]
    root = "/tmp/gie_base_local"
    n = 0
    for b in blobs:
        rel = b[len(prefix) + 1 :]  # e.g. region=aragua/part-0.parquet
        dst = os.path.join(root, rel)
        if os.path.exists(dst):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        _fetch(b, dst, settings, stage)
        n += 1
    print(f"  base: {len(blobs)} region files local ({n} newly downloaded)", flush=True)
    return os.path.join(root, "region=*", "*.parquet")


def _local(settings, layer, *parts, stage: str = STAGE) -> str:
    """Download a single input blob to local and return its path (DuckDB then
    reads locally). ALWAYS re-fetched, never cached: these silver / codab inputs
    are small and change between runs, so caching them would serve stale data
    (only the large, stable Overture base is cached — see _local_base)."""
    bp = settings.blob_path(layer, *parts)
    dst = os.path.join("/tmp/gie_local", bp)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    _fetch(bp, dst, settings, stage)
    return dst


def build_facts(res: int = DEFAULT_H3_RESOLUTION) -> pd.DataFrame:
    settings = load_settings(STAGE)
    # All inputs are mirrored to local disk (see _local/_local_base), so the
    # compute needs no blob access. Use a clean DuckDB connection WITHOUT the
    # azure extension — the azure-configured connection stalls the executor after
    # the flaky endpoint drops a connection mid-stream. Uploads use the Azure SDK.
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute("INSTALL h3 FROM community; LOAD h3;")
    con.execute("SET enable_progress_bar = false;")
    base = _local_base(settings)  # local disk — the blob read of the base stalls
    ms = _local(settings,"silver", "source=microsoft", f"adm0={ADM0}", "footprints.parquet")
    cems = _local(settings,
        "silver", "source=copernicus_ems", f"adm0={ADM0}", "builtup_damage.parquet"
    )
    analysed = _local(settings,
        "silver", "source=copernicus_ems", f"adm0={ADM0}", "analysed_extent.parquet"
    )
    ms_analysed = _local(settings,
        "silver", "source=microsoft", f"adm0={ADM0}", "analysed_extent.parquet"
    )
    # IMPACT SAR: per-building damaged set (damaged-only, ADR-0008) + footprint extent.
    sar = _local(settings,
        "silver", "source=impact_initiatives", f"adm0={ADM0}", "building_damage.parquet"
    )
    sar_ext = _local(settings,
        "silver", "source=impact_initiatives", f"adm0={ADM0}", "analysed_extent.parquet"
    )
    # HOT fAIr damage points (detected-only): snapped to the base like CEMS points.
    hot = _local(settings,
        "silver", "source=hot_osm", f"adm0={ADM0}", "damage_points.parquet"
    )
    # OSU S1 coherence: per-building damaged set (id-keyed to Overture) + extent (ADR-0009).
    osu = _local(settings,
        "silver", "source=osu", f"adm0={ADM0}", "building_damage.parquet"
    )
    osu_ext = _local(settings,
        "silver", "source=osu", f"adm0={ADM0}", "analysed_extent.parquet"
    )
    # DISHA (UN Global Pulse) damage points + AOI extent — snapped like HOT (LICENCE-gated).
    disha = _local(settings,
        "silver", "source=disha", f"adm0={ADM0}", "damage_points.parquet"
    )
    disha_ext = _local(settings,
        "silver", "source=disha", f"adm0={ADM0}", "analysed_extent.parquet"
    )
    adm3 = _local(settings,"bronze", "source=codab", f"adm0={ADM0}", "adm3.parquet")
    tol = SNAP_M / 111320.0  # ~degrees per metre (lat) for the snap buffer

    con.execute(
        f"""
        CREATE TEMP TABLE located AS
        WITH base AS (
            -- dedup by building id: adm1 pulls overlap each other and the old
            -- per-AOI pulls, so the same Overture building appears in >1 region
            SELECT id, geometry AS geom, ST_Centroid(geometry) AS c
            FROM read_parquet('{base}', hive_partitioning=true)
            QUALIFY row_number() OVER (PARTITION BY id) = 1
        ),
        ms_dmg AS (
            SELECT DISTINCT b.id FROM base b
            JOIN read_parquet('{ms}') m ON ST_Intersects(b.geom, m.geometry)
            WHERE m.damaged = 1 AND NOT m.superseded
        ),
        cems_latest AS (
            -- the authoritative latest CEMS layer per AOI (points where the
            -- monitoring update has landed, else the coarse area blocks)
            SELECT row_number() OVER () AS fid, layer_type, damage_class, geometry AS g
            FROM read_parquet('{cems}') WHERE is_latest
        ),
        cems_pt AS (
            -- snap each damage POINT to its nearest footprint within {SNAP_M} m
            -- (one point marks one building; ST_Distance is 0 when contained)
            SELECT id, damage_class FROM (
                SELECT b.id, l.damage_class,
                    row_number() OVER (PARTITION BY l.fid
                                       ORDER BY ST_Distance(b.geom, l.g)) AS rn
                FROM cems_latest l JOIN base b
                  ON l.layer_type = 'point'
                 AND ST_Intersects(ST_Buffer(l.g, {tol}), b.geom)
            ) WHERE rn = 1
        ),
        cems_area AS (
            -- coarse area blocks: every building the polygon covers
            SELECT b.id, l.damage_class FROM cems_latest l JOIN base b
              ON l.layer_type = 'area' AND ST_Intersects(b.geom, l.g)
        ),
        cems_dmg AS (
            -- worst grade wins when a building is hit by multiple features
            SELECT id, max(damage_class) AS cems_class
            FROM (SELECT * FROM cems_pt UNION ALL SELECT * FROM cems_area)
            GROUP BY id
        ),
        cems_coarse_set AS (
            -- coarse-block estimate: every building an area block covers (the
            -- CEMS reading available before the per-building points land)
            SELECT DISTINCT b.id FROM base b
            JOIN read_parquet('{cems}') x
              ON x.layer_type = 'area' AND ST_Intersects(b.geom, x.geometry)
        ),
        cems_seen AS (
            SELECT DISTINCT b.id FROM base b
            JOIN read_parquet('{analysed}') e ON ST_Intersects(b.geom, e.geometry)
        ),
        ms_seen AS (
            -- MS only assessed within its valid-area masks; elsewhere it has no
            -- data, which is different from "assessed, zero damage". Superseded
            -- AOIs (enclosed by a newer assessment) are excluded.
            SELECT DISTINCT b.id FROM base b
            JOIN read_parquet('{ms_analysed}') e ON ST_Within(b.c, e.geometry)
            WHERE NOT e.superseded
        ),
        sar_dmg AS (
            -- IMPACT v2: flag the base building that CONTAINS a v2 damaged
            -- footprint's centroid. v2 footprints ARE Overture (identical geometry),
            -- so centroid-containment is a clean 1:1 match onto the exact twin — no
            -- edge-neighbour over-flag (ST_Intersects gave ~86k vs the product's
            -- 81,437), and no id needed, so it still catches the 13,433 blank-id
            -- national footprints an id-join would drop (ADR-0015). Use
            -- ST_PointOnSurface (a point guaranteed INSIDE the footprint), not
            -- ST_Centroid — the centroid can fall outside concave/multipart shapes and
            -- miss an existing base twin. Any residual vs the product's 81,437 is now
            -- footprints with no Overture base twin (national footprints absent from our
            -- release); a base-flag count can't reach those — TODO count v2 rows
            -- directly if that gap ever matters.
            SELECT DISTINCT b.id FROM base b
            JOIN read_parquet('{sar}') s ON ST_Contains(b.geom, ST_PointOnSurface(s.geometry))
        ),
        sar_seen AS (
            -- IMPACT-analysed = inside the v2 analysed-area polygon (ADR-0015)
            SELECT DISTINCT b.id FROM base b
            JOIN read_parquet('{sar_ext}') e ON ST_Within(b.c, e.geometry)
        ),
        hot_dmg AS (
            -- fAIr damage POINTS snapped to the nearest base footprint within
            -- {SNAP_M} m (same rule as CEMS points): one point marks one building.
            SELECT id FROM (
                SELECT b.id,
                    row_number() OVER (PARTITION BY p.fid
                                       ORDER BY ST_Distance(b.geom, p.g)) AS rn
                FROM (SELECT row_number() OVER () AS fid, geometry AS g
                      FROM read_parquet('{hot}')) p
                JOIN base b ON ST_Intersects(ST_Buffer(p.g, {tol}), b.geom)
            ) WHERE rn = 1
        ),
        osu_seen AS (
            -- OSU-analysed = inside the analyzed-area polygon
            SELECT DISTINCT b.id FROM base b
            JOIN read_parquet('{osu_ext}') e ON ST_Within(b.c, e.geometry)
        ),
        disha_dmg AS (
            -- DISHA damage POINTS snapped to the nearest base footprint within
            -- {SNAP_M} m (same rule as HOT/CEMS points). LICENCE-gated preview.
            SELECT id FROM (
                SELECT b.id,
                    row_number() OVER (PARTITION BY p.fid
                                       ORDER BY ST_Distance(b.geom, p.g)) AS rn
                FROM (SELECT row_number() OVER () AS fid, geometry AS g
                      FROM read_parquet('{disha}')) p
                JOIN base b ON ST_Intersects(ST_Buffer(p.g, {tol}), b.geom)
            ) WHERE rn = 1
        ),
        disha_seen AS (
            -- DISHA-analysed = inside its AOI polygon
            SELECT DISTINCT b.id FROM base b
            JOIN read_parquet('{disha_ext}') e ON ST_Within(b.c, e.geometry)
        )
        SELECT b.id,
            round(ST_X(b.c), 6) AS lon, round(ST_Y(b.c), 6) AS lat,
            h3_h3_to_string(h3_latlng_to_cell(ST_Y(b.c), ST_X(b.c), {res})) AS h3,
            a.adm0_id, a.adm0_name, a.adm1_id, a.adm1_name,
            a.adm2_id, a.adm2_name, a.adm3_id, a.adm3_name,
            (b.id IN (SELECT id FROM ms_dmg)) AS ms_dmg,
            (b.id IN (SELECT id FROM ms_seen)) AS ms_analysed,
            (cd.id IS NOT NULL) AS cems_dmg,
            cd.cems_class AS cems_class,
            (b.id IN (SELECT id FROM cems_coarse_set)) AS cems_coarse,
            (b.id IN (SELECT id FROM cems_seen)) AS cems_analysed,
            (b.id IN (SELECT id FROM sar_dmg)) AS sar_dmg,
            IF(b.id IN (SELECT id FROM sar_dmg), 2, NULL) AS sar_class,
            (b.id IN (SELECT id FROM sar_seen)) AS sar_analysed,
            (b.id IN (SELECT id FROM hot_dmg)) AS hot_dmg,
            (od.id IS NOT NULL) AS osu_dmg,
            od.damage_class AS osu_class,
            (b.id IN (SELECT id FROM osu_seen)) AS osu_analysed,
            (b.id IN (SELECT id FROM disha_dmg)) AS disha_dmg,
            (b.id IN (SELECT id FROM disha_seen)) AS disha_analysed
        FROM base b
        LEFT JOIN read_parquet('{adm3}') a ON ST_Within(b.c, a.geometry)
        LEFT JOIN cems_dmg cd ON cd.id = b.id
        LEFT JOIN read_parquet('{osu}') od ON od.id = b.id
        """
    )
    print("  located table built", flush=True)

    # Run each per-source-per-grain aggregation as its own query and melt in
    # pandas (same pattern as _area_facts / _cems_breakdown below). The earlier
    # single-query form (15 SELECTs UNION ALL'd then UNPIVOT'd) wedged the DuckDB
    # executor at 3 sources for reasons not yet understood — each GROUP BY on its
    # own is trivial, so this sidesteps it. See docs/handoff-sar.md.
    parts = []
    for src, flag, analysed_expr in SOURCES:
        for unit_type, idcol, namecol in GRAINS:
            name_expr = "NULL" if namecol is None else f"any_value({namecol})"
            where = "" if unit_type == "h3" else f"WHERE {idcol} IS NOT NULL"
            parts.append(
                con.execute(
                    f"""
                    SELECT '{src}' AS source, '{METHOD}' AS method, '{unit_type}' AS unit_type,
                           {idcol} AS unit_id, {name_expr} AS unit_name,
                           count(*)::DOUBLE AS exposed_buildings,
                           ({analysed_expr})::DOUBLE AS analysed_buildings,
                           ({analysed_expr}) * 1.0 / count(*) AS coverage_fraction,
                           sum({flag}::INT)::DOUBLE AS damaged_detected,
                           CASE WHEN ({analysed_expr}) >= 0.25 * count(*)
                                THEN sum({flag}::INT) * 1.0 / ({analysed_expr}) * count(*)
                                ELSE NULL END AS damaged_extrapolated
                    FROM located {where} GROUP BY {idcol}
                    """
                ).df()
            )
    print("  facts aggregated (per-grain, pandas melt)", flush=True)
    df = pd.concat(parts, ignore_index=True).melt(
        id_vars=["source", "method", "unit_type", "unit_id", "unit_name"],
        value_vars=[
            "exposed_buildings", "analysed_buildings", "coverage_fraction",
            "damaged_detected", "damaged_extrapolated",
        ],
        var_name="metric",
        value_name="value",
    )
    # Persist per-building damage/coverage flags for the agreement layer. Only
    # assessed buildings are ever used there, and the full base is now millions
    # of rows (a single blob write would time out), so keep just the assessed.
    # TEMPORARY (ADR-0008, ADR-0009): the SAR and OSU sources contribute only their
    # DAMAGED buildings to the per-building layer, NOT their full analysed sets
    # (~1.9M / ~2.1M) — the untiled agreement view and a single blob write can't take that.
    # Rectify with PMTiles: then add `OR sar_analysed`/`OR osu_analysed` and carry
    # the analysed flags through.
    flags = con.execute(
        "SELECT id, lon, lat, ms_dmg, ms_analysed, cems_dmg, cems_class, cems_analysed, "
        "sar_dmg, sar_class, hot_dmg, osu_dmg, osu_class, disha_dmg "
        "FROM located WHERE ms_analysed OR cems_analysed OR sar_dmg OR hot_dmg OR osu_dmg OR disha_dmg"
    ).df()
    print(f"  building_flags computed ({len(flags):,} rows), uploading", flush=True)
    fpath = settings.blob_path("gold", "model=common", f"adm0={ADM0}", "building_flags.parquet")
    _upload(flags, fpath, settings)
    print(f"building_flags <- {fpath} ({len(flags):,} buildings)")

    # areal coverage: polygon area of each source's valid extent per admin unit
    df = pd.concat([df, _area_facts(con, settings)], ignore_index=True)
    # per-unit CEMS grade breakdown + coarse-block estimate (hover detail)
    df = pd.concat([df, _cems_breakdown(con)], ignore_index=True)
    df["ingested_at"] = pd.Timestamp.now("UTC")
    return df


def _area_facts(con, settings) -> pd.DataFrame:
    """Area of each source's valid (analysed) extent within each admin unit.

    Polygon area on the WGS84 spheroid (km^2), plus area coverage = that area
    divided by the unit's own area. Distinct from the building-count coverage:
    this is areal, the answer to "how much of the unit did each source image?".
    """
    sources = {
        "microsoft": (
            _local(settings,
                "silver", "source=microsoft", f"adm0={ADM0}", "analysed_extent.parquet"
            ),
            "WHERE NOT superseded",  # exclude AOIs enclosed by a newer assessment
        ),
        "copernicus_ems": (
            _local(settings,
                "silver", "source=copernicus_ems", f"adm0={ADM0}", "analysed_extent.parquet"
            ),
            "",  # CEMS supersession is handled upstream (active_products)
        ),
        "impact_initiatives": (
            _local(settings,
                "silver", "source=impact_initiatives", f"adm0={ADM0}", "analysed_extent.parquet"
            ),
            "",  # SAR footprint = raster bounds (ADR-0008)
        ),
        "osu": (
            _local(settings,
                "silver", "source=osu", f"adm0={ADM0}", "analysed_extent.parquet"
            ),
            "",  # OSU footprint = analyzed-area polygon (ADR-0009)
        ),
    }
    parts = []
    for src, (ext, where) in sources.items():
        for unit_type, idcol, namecol in GRAINS:
            if namecol is None:  # skip h3
                continue
            adm = _local(settings,"bronze", "source=codab", f"adm0={ADM0}", f"{unit_type}.parquet")
            parts.append(
                con.execute(
                    f"""
                    WITH u AS (
                        SELECT ST_Union_Agg(ST_MakeValid(geometry)) AS g
                        FROM read_parquet('{ext}') {where}
                    )
                    SELECT '{src}' AS source, '{METHOD}' AS method, '{unit_type}' AS unit_type,
                           a.{idcol} AS unit_id, a.{namecol} AS unit_name,
                           ST_Area_Spheroid(ST_Intersection(u.g, ST_MakeValid(a.geometry)))
                               / 1e6 AS analysed_area_km2,
                           ST_Area_Spheroid(ST_MakeValid(a.geometry)) / 1e6 AS unit_area_km2
                    FROM read_parquet('{adm}') a, u
                    WHERE ST_Intersects(u.g, a.geometry)
                    """
                ).df()
            )
    df = pd.concat(parts, ignore_index=True)
    df["area_coverage_fraction"] = df["analysed_area_km2"] / df["unit_area_km2"]
    return df.melt(
        id_vars=["source", "method", "unit_type", "unit_id", "unit_name"],
        value_vars=["analysed_area_km2", "unit_area_km2", "area_coverage_fraction"],
        var_name="metric",
        value_name="value",
    )


def _cems_breakdown(con) -> pd.DataFrame:
    """Per-unit CEMS hover breakdown: snapped damaged buildings by grade (sums to
    damaged_detected) and the coarse-block estimate (the area-block reading shown
    before the per-building points land)."""
    parts = []
    for unit_type, idcol, namecol in GRAINS:
        name_expr = "NULL" if namecol is None else f"any_value({namecol})"
        where = "" if unit_type == "h3" else f"WHERE {idcol} IS NOT NULL"
        parts.append(
            con.execute(
                f"""
                SELECT 'copernicus_ems' AS source, '{METHOD}' AS method,
                       '{unit_type}' AS unit_type, {idcol} AS unit_id,
                       {name_expr} AS unit_name,
                       sum((cems_class = 3)::INT)::DOUBLE AS cems_destroyed,
                       sum((cems_class = 2)::INT)::DOUBLE AS cems_damaged,
                       sum((cems_class = 1)::INT)::DOUBLE AS cems_possibly,
                       sum(cems_coarse::INT)::DOUBLE AS cems_coarse_detected
                FROM located {where} GROUP BY {idcol}
                """
            ).df()
        )
    df = pd.concat(parts, ignore_index=True)
    return df.melt(
        id_vars=["source", "method", "unit_type", "unit_id", "unit_name"],
        value_vars=["cems_destroyed", "cems_damaged", "cems_possibly", "cems_coarse_detected"],
        var_name="metric",
        value_name="value",
    )


def main() -> None:
    settings = load_settings(STAGE)
    df = build_facts()

    # Sanity: CEMS coverage + detected vs extrapolated at adm3 (where it has data).
    w = df[df.unit_type == "adm3"].pivot_table(
        index=["source", "unit_name"], columns="metric", values="value"
    )
    cems = w.loc["copernicus_ems"]
    cems = cems[cems["damaged_detected"] > 0].sort_values("damaged_detected", ascending=False)
    print("CEMS adm3 — coverage shrinks detected; extrapolation lifts it to full unit:")
    print(
        cems[
            ["exposed_buildings", "coverage_fraction", "damaged_detected", "damaged_extrapolated"]
        ].round(2).head(6).to_string()
    )

    gold = settings.blob_path("gold", "model=common", f"adm0={ADM0}", "facts.parquet")
    _upload(df, gold, settings)
    print(f"gold <- {gold} ({len(df):,} fact rows)")
    ledger.record(
        "common",
        "gold",
        "Common-model damage facts (Overture base, coverage-aware)",
        gold,
        f"{len(df):,} rows; exposed/analysed/coverage/detected/extrapolated per source",
    )


if __name__ == "__main__":
    main()
