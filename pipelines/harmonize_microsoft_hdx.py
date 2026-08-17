"""Silver: harmonise the Microsoft Colombia HDX deliveries onto the common schema.

Companion to ingest_microsoft_hdx.py (Colombia earthquake, per-city deliveries:
Pereira / Vantor 2026-08-12 and Cali / Airbus 2026-08-10). Each city ships
predictions on TWO footprint bases; we harmonize the OVERTURE base: its `id` is
the Overture GERS id, giving a clean id-keyed join to the common-model exposure
base and a consistent denominator (the Google-base gpkgs stay bronze-only, for
evaluation). Reprojects EPSG:32618 -> 4326 and writes the Microsoft silver
footprints.parquet + analysed_extent.parquet in the same schema as the VE
Microsoft silver (damaged/damage_pct_10m/aoi/superseded/adm0/source/geometry),
so harmonize_common + serving treat it as a drop-in.

Cloud cover: unlike VE's merged mask (cloud holes cut out), the CO valid-area
masks are single polygons and cloud cover is per-building `unknown_pct` — that
column is carried through so the coverage-aware common model can treat cloudy
buildings explicitly (not-analysed) rather than silently counting them as
assessed-intact.

Bronze filenames carry sensor + acquisition date, so the gpkg/mask per city are
resolved by pattern from the bronze listing — exactly one match each, or this
fails loudly (a second delivery date means a supersession decision, not a guess).

Run: uv run --group etl python pipelines/harmonize_microsoft_hdx.py
"""

from __future__ import annotations

import fnmatch
import os
import tempfile

import geopandas as gpd
import ocha_stratus as stratus
import pandas as pd

from gie import blob, events, ledger
from gie.config import load_settings, source_segments

SOURCE = "microsoft"
ADM0 = "CO"  # column value only — CO paths carry no adm0 segment (ADR-0027)
STAGE = "dev"
EVENT = "20260810-co-earthquake"  # validated against events.yaml in main()
AOIS = ("pereira", "cali")
FOOTPRINTS_GLOB = "*overture*_with_predictions.gpkg"
MASK_GLOB = "*valid_area_mask*.geojson"


def _bronze_file(settings, listing: list[str], aoi: str, pattern: str) -> str:
    """The single bronze blob under aoi=<aoi>/ matching pattern — else raise."""
    prefix = settings.blob_path("bronze", f"source={SOURCE}", f"aoi={aoi}", event=EVENT)
    hits = [b for b in listing if b.startswith(prefix + "/")
            and fnmatch.fnmatch(b.rsplit("/", 1)[-1], pattern)]
    if len(hits) != 1:
        raise RuntimeError(
            f"expected exactly one {pattern!r} in bronze for aoi={aoi}, found {hits} — "
            "a new delivery needs a deliberate supersession decision."
        )
    return hits[0]


def _read(settings, blob_name: str) -> gpd.GeoDataFrame:
    data = stratus.load_blob_data(blob_name, stage=STAGE, container_name=settings.container)
    suffix = os.path.splitext(blob_name)[1]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
        tf.write(data)
        tmp = tf.name
    gdf = gpd.read_file(tmp)
    os.unlink(tmp)
    return gdf


def main() -> None:
    events.require_event(EVENT)
    settings = load_settings(STAGE)
    listing = list(
        stratus.list_container_blobs(
            name_starts_with=settings.blob_path("bronze", f"source={SOURCE}", event=EVENT),
            stage=STAGE,
            container_name=settings.container,
        )
    )

    foot_parts, mask_parts, src_files = [], [], []
    for aoi in AOIS:
        fp_blob = _bronze_file(settings, listing, aoi, FOOTPRINTS_GLOB)
        mk_blob = _bronze_file(settings, listing, aoi, MASK_GLOB)
        src_files += [fp_blob.rsplit("/", 1)[-1], mk_blob.rsplit("/", 1)[-1]]

        fp = _read(settings, fp_blob).to_crs(4326)
        keep = fp[["id", "damaged", "damage_pct_10m", "unknown_pct", "geometry"]].copy()
        keep["damaged"] = keep["damaged"].astype("int64")
        keep["aoi"] = aoi
        foot_parts.append(keep)

        mask = _read(settings, mk_blob).to_crs(4326)
        mask_parts.append(mask[["geometry"]].assign(aoi=aoi))
        print(
            f"  {aoi}: {len(keep):,} buildings ({int(keep['damaged'].sum()):,} damaged), "
            f"{int((keep['unknown_pct'] > 0).sum()):,} cloud-affected; "
            f"mask {len(mask)} polygon(s)",
            flush=True,
        )

    foot = gpd.GeoDataFrame(pd.concat(foot_parts, ignore_index=True), crs="EPSG:4326")
    foot["superseded"] = False
    foot["adm0"] = ADM0
    foot["source"] = SOURCE
    fblob = settings.blob_path(
        "silver", *source_segments(SOURCE, EVENT), "footprints.parquet", event=EVENT
    )
    blob.upload_parquet_staged(foot, fblob, settings)
    n_dmg = int(foot["damaged"].sum())
    n_cloud = int((foot["unknown_pct"] > 0).sum())
    print(f"silver <- {fblob} ({len(foot):,} buildings, {n_dmg:,} damaged)", flush=True)

    ext = gpd.GeoDataFrame(pd.concat(mask_parts, ignore_index=True), crs="EPSG:4326")
    ext["superseded"] = False
    ext["adm0"] = ADM0
    ext["source"] = SOURCE
    eblob = settings.blob_path(
        "silver", *source_segments(SOURCE, EVENT), "analysed_extent.parquet", event=EVENT
    )
    blob.upload_parquet_staged(ext, eblob, settings)
    print(f"silver <- {eblob} ({len(ext)} valid-area polygons)", flush=True)

    ledger.record(
        SOURCE,
        "silver",
        "Microsoft CO HDX deliveries harmonised to silver (Overture base)",
        fblob,
        f"{len(foot):,} Overture-base buildings ({n_dmg:,} damaged, {n_cloud:,} with "
        f"unknown_pct>0 cloud) across {', '.join(AOIS)}; id = Overture GERS; per-city "
        f"valid-area masks as analysed extent; Google-base gpkgs bronze-only; "
        f"from {', '.join(src_files)}",
        status="ingesting",
    )


if __name__ == "__main__":
    main()
