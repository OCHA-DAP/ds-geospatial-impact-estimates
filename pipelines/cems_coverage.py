"""Extract the CEMS analysed extent (coverage mask) -> silver.

Registry-driven, one event per run: ``--event <event_id>`` names the event and
the activation comes from its ``external_ids.cems_activation`` (ADR-0027; same
pattern as ingest_cems / harmonize_cems).

CEMS only assesses where it has cloud-free imagery, so its damage counts are a
lower bound biased by coverage. The *analysed* extent per AOI is the image
footprint clipped to the area of interest, minus the not-analysed parts:

    (imageFootprintA INTERSECT areaOfInterestA) - notAnalysedA

imageFootprintA alone is the whole satellite scene (far larger than the tasked
area), so it is clipped to areaOfInterestA; notAnalysedA removes cloud / no-data
holes. All these shapefiles live in the bronze GRA product zips. Downstream, the
share of an admin unit's buildings inside this extent is its CEMS coverage, and
the observed damage rate can be extrapolated to the rest of the unit (see
harmonize_common).

Products to use (and which is the latest per AOI) come from
``gie.cems_products.active_products`` — superseded versions are dropped and every
shape is tagged with the manifest's own metadata, so coverage and damage agree.

Run: uv run --group etl python pipelines/cems_coverage.py --event 20260810-co-earthquake
"""

from __future__ import annotations

import argparse

import geopandas as gpd
import ocha_stratus as stratus
import pandas as pd

from gie import events, ledger
from gie.cems_products import active_products, read_layer
from gie.config import load_settings, source_segments

SOURCE = "copernicus_ems"
STAGE = "dev"


def _meta(p) -> dict:
    """Per-product tags straight from the CEMS manifest (see cems_products).

    ``product``/``acquired`` are display fields derived from the real fields that
    travel alongside (``monitoring_number``, ``version_number``, ``delivery_time``).
    """
    acq = (
        pd.to_datetime(p.delivery_time).strftime("%Y-%m-%d")
        if pd.notna(p.delivery_time)
        else "—"
    )
    return {
        "src_zip": p.zip_name,
        "aoi": int(p.aoi_number),
        "aoi_name": p.aoi_name,
        "product_id": int(p.product_id),
        "monitoring_number": int(p.monitoring_number),
        "version_number": int(p.version_number),
        "product": p.label,
        "acquired": acq,
        "is_latest": bool(p.is_latest),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--event",
        required=True,
        help="event_id from events.yaml; its external_ids.cems_activation is processed",
    )
    args = parser.parse_args()
    ev = events.get_event(args.event)  # fails loudly on an unregistered event
    activation = ev.external_ids.get("cems_activation")
    if not activation:
        raise RuntimeError(
            f"event {ev.event_id!r} has no external_ids.cems_activation in events.yaml."
        )
    settings = load_settings(STAGE)
    products = active_products(settings, activation, event=ev.event_id, stage=STAGE)
    products = products[products["product_type"] == "GRA"]

    bronze = settings.blob_path(
        "bronze", f"source={SOURCE}", f"code={activation}", event=ev.event_id
    )
    zip_by_name = {
        b.split("/")[-1]: b
        for b in stratus.list_container_blobs(
            name_starts_with=bronze, stage=STAGE, container_name=settings.container
        )
        if b.endswith(".zip")
    }

    analysed_parts, detail_parts, used = [], [], 0
    for p in products.itertuples():
        blob = zip_by_name.get(p.zip_name)
        if blob is None:
            continue  # active product not downloaded to bronze yet
        data = stratus.load_blob_data(blob, stage=STAGE, container_name=settings.container)
        # Valid analysed area = Area of Interest minus the Not-Analysed (cloud /
        # no-imagery) parts within it.
        aoi = read_layer(data, "areaOfInterestA")
        if aoi is None or len(aoi) == 0:
            continue
        ifp = read_layer(data, "imageFootprintA")
        not_analysed = read_layer(data, "notAnalysedA")

        # Image area actually analysed = image footprint clipped to the AOI (the
        # footprint alone is the whole satellite scene, far larger than the
        # tasked area), minus the not-analysed (cloud / no-data) parts within it.
        analysed = aoi[["geometry"]]
        if ifp is not None and len(ifp):
            analysed = gpd.overlay(analysed, ifp[["geometry"]], how="intersection")
        if not_analysed is not None and len(not_analysed):
            analysed = gpd.overlay(analysed, not_analysed[["geometry"]], how="difference")

        meta = _meta(p)
        analysed_parts.append(analysed.assign(**meta))
        # the analysed shape + the cloud gaps, with per-product metadata for hover
        detail_parts.append(analysed[["geometry"]].assign(kind="analysed", **meta))
        if not_analysed is not None and len(not_analysed):
            detail_parts.append(
                not_analysed[["geometry"]].assign(kind="not_analysed", **meta)
            )
        used += 1
        flag = " [latest]" if p.is_latest else ""
        print(f"  {p.zip_name}: {p.aoi_name} / {p.label} ({meta['acquired']}){flag}", flush=True)

    if not analysed_parts:
        raise RuntimeError(
            f"no areaOfInterestA layer found in any live {activation} GRA product — "
            "bronze products missing or product structure changed."
        )
    analysed_gdf = gpd.GeoDataFrame(pd.concat(analysed_parts, ignore_index=True), crs="EPSG:4326")
    out = settings.blob_path(
        "silver", *source_segments(SOURCE, ev.event_id), "analysed_extent.parquet",
        event=ev.event_id,
    )
    stratus.upload_parquet_to_blob(
        analysed_gdf, out, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"silver <- {out} ({len(analysed_gdf)} analysed polygons from {used} live products)")

    detail_gdf = gpd.GeoDataFrame(pd.concat(detail_parts, ignore_index=True), crs="EPSG:4326")
    dout = settings.blob_path(
        "silver", *source_segments(SOURCE, ev.event_id), "coverage_detail.parquet",
        event=ev.event_id,
    )
    stratus.upload_parquet_to_blob(
        detail_gdf, dout, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"silver <- {dout} (analysed + not-analysed shapes for display)")

    ledger.record(
        SOURCE,
        "silver",
        f"CEMS {activation} analysed extent (AOI - not-analysed) + coverage detail",
        out,
        f"{len(analysed_gdf)} analysed polygons; AOI/not-analysed shapes for display",
        status="ingesting",
    )


if __name__ == "__main__":
    main()
