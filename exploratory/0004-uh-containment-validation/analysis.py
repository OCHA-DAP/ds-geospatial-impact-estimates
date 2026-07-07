"""Validate the v2 containment rule for the id-less UH footprints (ADR-0015/0018).

UH damage predictions are graded footprints that ARE ~Overture geometry but carry
no id, so harmonize_common projects a UH damaged/destroyed footprint onto the base
by centroid-containment: a base building is flagged when it CONTAINS the footprint's
point-on-surface (`ST_Contains(base, ST_PointOnSurface(uh))`, the impact_v2 rule).

This confirms the rule is clean by counting, per AOI:
  * native      — UH footprints graded damaged/destroyed (the source's own count)
  * matched     — of those, how many have their point-on-surface inside SOME base
                  building (i.e. an Overture twin exists) -> match rate
  * projected   — DISTINCT base buildings flagged (what the pipeline reports)
  * collapse    — matched - projected: UH footprints sharing one base building
                  (UH finer than Overture); should be near zero if 1:1

A near-100% match rate and near-zero collapse = the join is a clean 1:1 and the
projected damaged count faithfully reproduces the native one. Big gaps would mean
UH footprints without Overture twins (drop) or many-to-one snapping (undercount).

Run: GIE_BLOB_ACCOUNT_PREFIX=imb0chd0 uv run --group etl python \
       exploratory/0004-uh-containment-validation/analysis.py
"""

from __future__ import annotations

import os
import sys

import duckdb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "pipelines"))
import harmonize_common as hc  # noqa: E402  (reuse the exact base cache + local fetch)

from gie.config import load_settings  # noqa: E402

ADM0 = "VE"


def main() -> None:
    settings = load_settings("dev")
    base = hc._local_base(settings)  # cached Overture VE base (hive glob)
    uh = hc._local(settings, "silver", "source=uh", f"adm0={ADM0}", "footprints.parquet")

    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute("SET enable_progress_bar = false;")

    con.execute(
        f"""
        CREATE TEMP TABLE base AS
        SELECT id, geometry AS geom FROM read_parquet('{base}', hive_partitioning=true)
        QUALIFY row_number() OVER (PARTITION BY id) = 1;

        CREATE TEMP TABLE dmg AS
        SELECT row_number() OVER () AS uid, aoi, grade,
               ST_PointOnSurface(geometry) AS pt
        FROM read_parquet('{uh}') WHERE grade <> 'intact';

        -- each damaged UH footprint -> the base building containing its PoS (if any)
        CREATE TEMP TABLE hit AS
        SELECT d.uid, d.aoi, b.id AS base_id
        FROM dmg d LEFT JOIN base b ON ST_Contains(b.geom, d.pt);
        """
    )

    per_aoi = con.execute(
        """
        SELECT aoi,
               count(DISTINCT uid)                              AS native,
               count(DISTINCT uid) FILTER (base_id IS NOT NULL) AS matched,
               count(DISTINCT base_id)                          AS projected
        FROM hit GROUP BY aoi ORDER BY aoi
        """
    ).df()
    per_aoi["match_rate"] = (per_aoi["matched"] / per_aoi["native"]).round(4)
    per_aoi["collapse"] = per_aoi["matched"] - per_aoi["projected"]

    tot = per_aoi[["native", "matched", "projected", "collapse"]].sum()
    print("Per-AOI containment validation (UH damaged/destroyed footprints):\n")
    print(per_aoi.to_string(index=False))
    print(
        f"\nTOTAL  native={int(tot.native):,}  matched={int(tot.matched):,} "
        f"({tot.matched / tot.native:.2%})  projected={int(tot.projected):,}  "
        f"collapse={int(tot.collapse):,}  unmatched={int(tot.native - tot.matched):,}"
    )

    # multiplicity detail: base buildings holding >1 damaged UH footprint
    multi = con.execute(
        "SELECT count(*) FILTER (WHERE n > 1) AS shared_base, max(n) AS max_per_base "
        "FROM (SELECT base_id, count(*) n FROM hit WHERE base_id IS NOT NULL GROUP BY base_id)"
    ).df()
    print(
        f"base buildings holding >1 UH damaged footprint: {int(multi.shared_base[0]):,} "
        f"(max {int(multi.max_per_base[0])} per base)"
    )


if __name__ == "__main__":
    main()
