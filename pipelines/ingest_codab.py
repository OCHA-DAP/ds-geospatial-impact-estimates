"""One-time loader: OCHA CODAB admin boundaries (adm 0-3) from FieldMaps.

Pulls the canonical edge-matched CODs via ocha-stratus' FieldMaps loader and
writes each level to bronze as EPSG:4326 GeoParquet for DuckDB to query. These
boundaries are the reporting/aggregation layer for the harmonization model
(see docs/decisions/0001).

Run: uv run --group etl python pipelines/ingest_codab.py --iso3 COL --adm0 CO
"""

from __future__ import annotations

import argparse

import ocha_stratus as stratus
from ocha_stratus.datasources.codab import load_codab_from_fieldmaps

from gie import ledger
from gie.config import load_settings

STAGE = "dev"
DEFAULT_LEVELS = "0,1,2,3"


def _padding_evidence(gdf, level: int) -> str | None:
    """Detect FieldMaps padding a country's COD hierarchy: when a country's
    real subdivisions stop short of `level`, FieldMaps' global adm{level}
    dataset repeats the deepest real level's rows into the adm{level} slot
    instead of returning nothing for that country. Returns an evidence string
    if `gdf` looks like padding rather than a genuine level, else None.

    Three signals, any one of which is sufficient:
      - adm{level}_src is entirely null (no source code was ever recorded at
        this level for this country)
      - adm{level}_id duplicates adm{level-1}_id row-for-row (the "new" level
        is just a copy of its parent)
      - `level` exceeds the deepest level this country's source data actually
        reaches

    On that third signal: src_lvl is a country-wide "deepest digitized
    source level" attribute that FieldMaps copies onto every row of every
    admin-level file for that country — NOT a per-file "this is level N"
    marker. A real, shallower level (e.g. a real adm1 file for a country
    whose source only ever reaches adm2) will legitimately show
    src_lvl == [2], not [1]. So the check has to be "level > max(src_lvl)",
    not "level not in src_lvl" — the latter would misfire on real adm1/adm2
    files for exactly this kind of country (confirmed empirically against
    Colombia's real adm1/adm2 blobs, both src_lvl == [2], and against
    Venezuela's real adm3, src_lvl containing 3).
    """
    src_col, id_col, prev_id_col = f"adm{level}_src", f"adm{level}_id", f"adm{level - 1}_id"
    all_null_src = src_col in gdf.columns and gdf[src_col].isna().all()
    ids_duplicate_prev = (
        id_col in gdf.columns
        and prev_id_col in gdf.columns
        and set(gdf[id_col]) == set(gdf[prev_id_col])
    )
    src_lvls = gdf["src_lvl"].dropna() if "src_lvl" in gdf.columns else None
    exceeds_source_depth = src_lvls is not None and len(src_lvls) > 0 and level > src_lvls.max()
    if not (all_null_src or ids_duplicate_prev or exceeds_source_depth):
        return None
    seen = sorted(src_lvls.unique()) if src_lvls is not None else None
    return (
        f"src_lvl={seen}, {src_col}_all_null={all_null_src}, "
        f"ids_duplicate_prev={ids_duplicate_prev}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest OCHA CODAB admin boundaries (shared reference tree)")
    ap.add_argument("--iso3", required=True, help="country ISO3, e.g. VEN, COL")
    ap.add_argument("--adm0", required=True, help="adm0 partition code, e.g. VE, CO")
    ap.add_argument(
        "--levels",
        default=DEFAULT_LEVELS,
        help=f"comma-separated admin levels to attempt, default {DEFAULT_LEVELS}",
    )
    args = ap.parse_args()
    iso3, adm0 = args.iso3.upper(), args.adm0.upper()
    levels = tuple(int(x) for x in args.levels.split(","))

    settings = load_settings(STAGE)
    counts = {}
    skipped_padding: list[str] = []
    for level in levels:
        gdf = load_codab_from_fieldmaps(iso3, admin_level=level)
        if gdf is None or len(gdf) == 0:
            print(f"adm{level}: no data returned, skipping")
            continue
        gdf = gdf.to_crs(4326)
        if level > 0:
            evidence = _padding_evidence(gdf, level)
            if evidence is not None:
                print(
                    f"adm{level}: not a real level for {iso3} (FieldMaps padding "
                    f"detected — {evidence}); skipping"
                )
                skipped_padding.append(
                    f"adm{level}: not a real level for {iso3} (FieldMaps padding), skipped"
                )
                continue
        # event=None: CODAB is shared, country-keyed REFERENCE data outside the
        # event tree — reusable across events (spec §3).
        path = settings.blob_path(
            "bronze", "source=codab", f"adm0={adm0}", f"adm{level}.parquet", event=None
        )
        stratus.upload_parquet_to_blob(
            gdf, path, stage=STAGE, container_name=settings.container, compression="zstd"
        )
        counts[f"adm{level}"] = len(gdf)
        print(f"adm{level} <- {path}  ({len(gdf):,} features)")

    detail = "; ".join(f"{k}={v}" for k, v in counts.items()) + "; EPSG:4326"
    if skipped_padding:
        detail += "; " + "; ".join(skipped_padding)
    ledger.record(
        source="codab",
        layer="bronze",
        dataset=f"OCHA CODAB admin boundaries — {iso3} (FieldMaps)",
        path=settings.blob_path("bronze", "source=codab", f"adm0={adm0}", event=None),
        detail=detail,
    )


if __name__ == "__main__":
    main()
