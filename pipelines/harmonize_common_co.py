"""Common-model harmonization for the COLOMBIA earthquake: MS + CEMS on Overture.

Event-pinned (ADR-0027) companion to harmonize_common.py (the VE common model,
9 sources). Colombia currently has two harmonized sources, so this is the
two-source common model on the shared exposure base (ADR-0001):

  * Microsoft  -> three deliveries (pereira, cali, pereira_extended), merged
                  at silver with per-building supersession (the reviewed
                  extended run wins inside its mask; only active rows are read
                  here). Original deliveries are ALREADY on the Overture base
                  (id = GERS) and join by id; the extended delivery ships
                  row-index ids (nulled in silver), so its rows map spatially
                  by point-on-surface containment (ADR-0015). Cloud rule:
                  a building with unknown_pct > 0 was partially cloud-covered
                  and could not be fully assessed, so it is NOT analysed
                  (Microsoft's own HDX notes exclude them from denominators);
                  it still counts in damaged_detected if flagged (a floor).
                  The id-join match rate against our base is verified and the
                  run fails loudly below 95% (a release mismatch would silently
                  undercount otherwise).
  * Copernicus -> the latest CEMS product per AOI, each per-building damage
                  point snapped to its nearest footprint (<=20 m), worst grade
                  wins (EMSR916 shipped points only; the coarse-area path
                  remains for any later GRM/area product).

Coverage-aware metrics per unit (h3 + adm0-2 — CO has no real adm3):
exposed / analysed / coverage_fraction / damaged_detected / damaged_extrapolated,
plus areal coverage and the CEMS grade breakdown (same schema as VE, so the
platinum/serving layer is a drop-in).

New CO sources: add their CTE + SOURCES entry here (same shapes as
harmonize_common.py).

Run: uv run --group etl python pipelines/harmonize_common_co.py
"""

from __future__ import annotations

import pandas as pd

from gie import codab, events, ledger
from gie.blob import upload_parquet_staged
from gie.config import DEFAULT_H3_RESOLUTION, common_segments, load_settings, source_segments
from gie.localcache import local, local_base

METHOD = "common_overture_v1"
ADM0 = "CO"  # column value + CODAB key; CO paths carry no adm0 segment (ADR-0027)
STAGE = "dev"
EVENT = "20260810-co-earthquake"  # validated against events.yaml in main()

# CEMS per-building damage points (builtUpP) snapped to the nearest Overture
# footprint within this radius; 20 m matched 99.5% of points in EMSR884.
SNAP_M = 20
# Minimum share of Microsoft ids that must exist in our Overture base for the
# id-join to be trusted (below this, the bases are different releases and
# damage would silently undercount).
MIN_ID_MATCH = 0.95

# (source, damaged-flag, analysed-buildings expression) — see harmonize_common.
SOURCES = [
    ("microsoft", "ms_dmg", "sum(ms_analysed::INT)"),
    ("copernicus_ems", "cems_dmg", "sum(cems_analysed::INT)"),
]


def build_facts(settings, deepest: int, res: int = DEFAULT_H3_RESOLUTION) -> pd.DataFrame:
    # All inputs are mirrored to local disk (gie.localcache) — the compute needs
    # no blob access, so use a clean DuckDB connection WITHOUT the azure
    # extension (it stalls the executor after a dropped connection).
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute("INSTALL h3 FROM community; LOAD h3;")
    con.execute("SET enable_progress_bar = false;")

    base = local_base(
        settings,
        settings.blob_path("silver", *source_segments("overture", EVENT), event=EVENT),
        root=f"/tmp/gie_base_local-{EVENT}",
        stage=STAGE,
    )
    ms = local(settings, "silver", *source_segments("microsoft", EVENT),
               "footprints.parquet", event=EVENT, stage=STAGE)
    ms_ext = local(settings, "silver", *source_segments("microsoft", EVENT),
                   "analysed_extent.parquet", event=EVENT, stage=STAGE)
    cems = local(settings, "silver", *source_segments("copernicus_ems", EVENT),
                 "builtup_damage.parquet", event=EVENT, stage=STAGE)
    cems_ext = local(settings, "silver", *source_segments("copernicus_ems", EVENT),
                     "analysed_extent.parquet", event=EVENT, stage=STAGE)
    levels = [f"adm{i}" for i in range(deepest + 1)]
    # event=None: CODAB is shared, country-keyed REFERENCE data (spec §3). One
    # fetch per level for the whole run — CO adm2 is 81 MB, so it gets a stall
    # window a slow uplink can actually finish, and is never fetched twice.
    adm_paths = {
        lvl: local(settings, "bronze", "source=codab", f"adm0={ADM0}",
                   f"{lvl}.parquet", event=None, stage=STAGE, timeout_s=600)
        for lvl in levels
    }
    admin = adm_paths[f"adm{deepest}"]
    admin_cols = ", ".join(f"a.{lvl}_id, a.{lvl}_name" for lvl in levels)
    tol = SNAP_M / 111320.0  # ~degrees per metre (lat) for the snap buffer

    # Fail loudly if the Microsoft Overture ids don't match our base release
    # (GERS-id rows only — the extended delivery's rows are id-less by design).
    match = con.execute(
        f"""
        WITH base_ids AS (
            SELECT DISTINCT id FROM read_parquet('{base}', hive_partitioning=true)
        )
        SELECT count(*) AS total,
               sum((m.id IN (SELECT id FROM base_ids))::INT) AS matched
        FROM read_parquet('{ms}') m WHERE m.id IS NOT NULL
        """
    ).fetchone()
    total_ms, matched_ms = int(match[0]), int(match[1])
    rate = matched_ms / total_ms if total_ms else 0.0
    print(f"  MS id-join: {matched_ms:,}/{total_ms:,} ids in base ({rate:.1%})", flush=True)
    if rate < MIN_ID_MATCH:
        raise RuntimeError(
            f"Microsoft Overture-id match rate {rate:.1%} < {MIN_ID_MATCH:.0%} — the MS "
            "predictions and our base are different Overture releases; an id-join would "
            "silently undercount damage. Align the base release or switch to a spatial join."
        )

    con.execute(
        f"""
        CREATE TEMP TABLE located AS
        WITH base AS (
            -- dedup by building id: adm1 pulls overlap each other, so the same
            -- Overture building can appear in >1 region partition
            SELECT id, geometry AS geom, ST_Centroid(geometry) AS c
            FROM read_parquet('{base}', hive_partitioning=true)
            QUALIFY row_number() OVER (PARTITION BY id) = 1
        ),
        ms AS (
            -- active rows only: per-building supersession already resolved in
            -- silver (pereira defers to the reviewed pereira_extended inside
            -- its mask), so verdicts here never conflict
            SELECT id, damaged, unknown_pct, geometry AS g
            FROM read_parquet('{ms}') WHERE NOT superseded
        ),
        -- GERS-id rows join the base directly; id-less (extended) rows map by
        -- point-on-surface containment onto the exact Overture twin (ADR-0015)
        ms_dmg AS (
            SELECT id FROM ms WHERE damaged = 1 AND id IS NOT NULL
            UNION
            SELECT b.id FROM base b
            JOIN ms m ON m.id IS NULL AND m.damaged = 1
                     AND ST_Contains(b.geom, ST_PointOnSurface(m.g))
        ),
        ms_seen AS (
            -- analysed = listed by Microsoft AND fully cloud-free (see docstring)
            SELECT id FROM ms WHERE unknown_pct = 0 AND id IS NOT NULL
            UNION
            SELECT b.id FROM base b
            JOIN ms m ON m.id IS NULL AND m.unknown_pct = 0
                     AND ST_Contains(b.geom, ST_PointOnSurface(m.g))
        ),
        cems_latest AS (
            -- the authoritative latest CEMS layer per AOI
            SELECT row_number() OVER () AS fid, layer_type, damage_class, geometry AS g
            FROM read_parquet('{cems}') WHERE is_latest
        ),
        cems_pt AS (
            -- snap each damage POINT to its nearest footprint within {SNAP_M} m
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
            -- coarse area blocks: every building the polygon covers (none in
            -- EMSR916 so far — kept for any later GRM/area product)
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
            SELECT DISTINCT b.id FROM base b
            JOIN read_parquet('{cems}') x
              ON x.layer_type = 'area' AND ST_Intersects(b.geom, x.geometry)
        ),
        cems_seen AS (
            SELECT DISTINCT b.id FROM base b
            JOIN read_parquet('{cems_ext}') e ON ST_Intersects(b.geom, e.geometry)
        )
        SELECT b.id,
            round(ST_X(b.c), 6) AS lon, round(ST_Y(b.c), 6) AS lat,
            h3_h3_to_string(h3_latlng_to_cell(ST_Y(b.c), ST_X(b.c), {res})) AS h3,
            {admin_cols},
            (b.id IN (SELECT id FROM ms_dmg)) AS ms_dmg,
            (b.id IN (SELECT id FROM ms_seen)) AS ms_analysed,
            (cd.id IS NOT NULL) AS cems_dmg,
            cd.cems_class AS cems_class,
            (b.id IN (SELECT id FROM cems_coarse_set)) AS cems_coarse,
            (b.id IN (SELECT id FROM cems_seen)) AS cems_analysed
        FROM base b
        LEFT JOIN read_parquet('{admin}') a ON ST_Within(b.c, a.geometry)
        LEFT JOIN cems_dmg cd ON cd.id = b.id
        """
    )
    print("  located table built", flush=True)

    grains = [("h3", "h3", None)] + [(lvl, f"{lvl}_id", f"{lvl}_name") for lvl in levels]
    # Per-source-per-grain aggregation, melted in pandas (see harmonize_common on
    # why not one giant UNPIVOT query).
    parts = []
    for src, flag, analysed_expr in SOURCES:
        for unit_type, idcol, namecol in grains:
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

    # Per-building flags for the agreement layer (assessed buildings only).
    flags = con.execute(
        "SELECT id, lon, lat, ms_dmg, ms_analysed, cems_dmg, cems_class, cems_analysed "
        "FROM located WHERE ms_analysed OR cems_analysed OR ms_dmg OR cems_dmg"
    ).df()
    print(f"  building_flags computed ({len(flags):,} rows), uploading", flush=True)
    fpath = settings.blob_path(
        "gold", *common_segments(EVENT, ADM0), "building_flags.parquet", event=EVENT
    )
    upload_parquet_staged(flags, fpath, settings, stage=STAGE)
    print(f"building_flags <- {fpath} ({len(flags):,} buildings)")

    # areal coverage: polygon area of each source's valid extent per admin unit
    df = pd.concat(
        [df, _area_facts(con, {"microsoft": (ms_ext, "WHERE NOT superseded"),
                               "copernicus_ems": (cems_ext, "")}, adm_paths)],
        ignore_index=True,
    )
    # per-unit CEMS grade breakdown + coarse-block estimate (hover detail)
    df = pd.concat([df, _cems_breakdown(con, grains)], ignore_index=True)
    df["ingested_at"] = pd.Timestamp.now("UTC")
    return df


def _area_facts(con, sources: dict, adm_paths: dict[str, str]) -> pd.DataFrame:
    """Area of each source's valid (analysed) extent within each admin unit
    (spheroid km^2 + share of the unit's own area). Same semantics as VE."""
    parts = []
    for src, (ext, where) in sources.items():
        for lvl, adm in adm_paths.items():
            parts.append(
                con.execute(
                    f"""
                    WITH u AS (
                        SELECT ST_Union_Agg(ST_MakeValid(geometry)) AS g
                        FROM read_parquet('{ext}') {where}
                    )
                    SELECT '{src}' AS source, '{METHOD}' AS method, '{lvl}' AS unit_type,
                           a.{lvl}_id AS unit_id, a.{lvl}_name AS unit_name,
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


def _cems_breakdown(con, grains) -> pd.DataFrame:
    """Per-unit CEMS hover breakdown: snapped damaged buildings by grade (sums to
    damaged_detected) and the coarse-block estimate."""
    parts = []
    for unit_type, idcol, namecol in grains:
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
    events.require_event(EVENT)
    settings = load_settings(STAGE)
    deepest = codab.deepest_level(settings, ADM0, stage=STAGE)
    df = build_facts(settings, deepest)

    # Sanity: coverage + detected vs extrapolated at the deepest admin level.
    w = df[df.unit_type == f"adm{deepest}"].pivot_table(
        index=["source", "unit_name"], columns="metric", values="value"
    )
    for src in ("copernicus_ems", "microsoft"):
        s = w.loc[src]
        s = s[s["damaged_detected"] > 0].sort_values("damaged_detected", ascending=False)
        print(f"{src} adm{deepest} — coverage shrinks detected; extrapolation lifts it:")
        print(
            s[
                ["exposed_buildings", "coverage_fraction",
                 "damaged_detected", "damaged_extrapolated"]
            ].round(2).head(6).to_string()
        )

    gold = settings.blob_path("gold", *common_segments(EVENT, ADM0), "facts.parquet", event=EVENT)
    upload_parquet_staged(df, gold, settings, stage=STAGE)
    print(f"gold <- {gold} ({len(df):,} fact rows)")
    ledger.record(
        "common",
        "gold",
        "Common-model damage facts — Colombia earthquake (MS + CEMS, coverage-aware)",
        gold,
        f"{len(df):,} rows; exposed/analysed/coverage/detected/extrapolated per source; "
        "MS id-keyed to Overture (cloudy unknown_pct>0 = not analysed); CEMS points "
        "snapped <=20 m; adm0-2 (CO has no adm3)",
    )


if __name__ == "__main__":
    main()
