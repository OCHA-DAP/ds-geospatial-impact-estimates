"""Idempotent loader: Copernicus EMS Rapid Mapping damage products -> bronze.

Polls the Venezuela earthquake activation (EMSR884) via the ocha-lens `cems`
datasource (pinned to PR #49) and lands delivered product zips in bronze. CEMS
delivers products piecemeal over the life of an open activation, with version
and monitoring updates, so this loader is built to be re-run on any cadence:

  * each product version lands at a unique, immutable, version-encoded path;
  * already-present products are skipped (no re-download, no overwrite);
  * each poll writes a timestamped manifest snapshot of the activation state.

No central ledger DB yet — idempotency lives in the blob layout. See
docs/decisions/0005 (and 0001 for where this source fits the harmonization
model). Harmonizing the damage-grade polygons onto the exposure base / H3 grid
is a later (silver/gold) step; this only lands raw bronze.

Run: uv run --group etl python pipelines/ingest_cems.py
"""

from __future__ import annotations

import posixpath

import ocha_lens as lens
import ocha_stratus as stratus
import pandas as pd

from gie import ledger
from gie.config import load_settings

ACTIVATION = "EMSR884"
SOURCE = "copernicus_ems"
STAGE = "dev"


def _product_blob(settings, row, fname: str) -> str:
    """Immutable, version-encoded bronze key for one product version."""
    return settings.blob_path(
        "bronze",
        f"source={SOURCE}",
        f"code={ACTIVATION}",
        f"aoi={int(row['aoi_number']):02d}",
        f"product_type={row['product_type']}",
        f"v{int(row['version_number'])}_m{int(row['monitoring_number'])}",
        fname,
    )


def main() -> None:
    settings = load_settings(STAGE)
    container = stratus.get_container_client(stage=STAGE, container_name=settings.container)

    prods = lens.cems.get_products(ACTIVATION)

    # Immutable manifest snapshot, keyed by the latest product delivery time so a
    # re-poll with no new deliveries reuses the same snapshot name.
    latest = prods["delivery_time"].max()
    snap = (
        pd.to_datetime(latest).strftime("%Y%m%dT%H%M%S") if pd.notna(latest) else "pending"
    )
    manifest = settings.blob_path(
        "bronze", f"source={SOURCE}", f"code={ACTIVATION}", f"products_{snap}.parquet"
    )
    stratus.upload_parquet_to_blob(
        prods, manifest, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"manifest <- {manifest} ({len(prods)} products)")

    delivered = prods[prods["download_url"].notna()]
    downloaded = skipped = 0
    for _, row in delivered.iterrows():
        fname = posixpath.basename(str(row["download_url"]))
        blob_name = _product_blob(settings, row, fname)
        if container.get_blob_client(blob_name).exists():
            skipped += 1
            continue
        data = lens.cems.download_product(row, dest=None)
        lens.cems.to_blob(data, blob_name, stage=STAGE, container_name=settings.container)
        downloaded += 1
        print(f"  bronze <- {blob_name} ({len(data):,} bytes)")

    pending = len(prods) - len(delivered)
    ledger.record(
        source=SOURCE,
        layer="bronze",
        dataset=f"Copernicus EMS {ACTIVATION} — Venezuela earthquake damage products",
        path=settings.blob_path("bronze", f"source={SOURCE}", f"code={ACTIVATION}"),
        detail=f"{len(delivered)} delivered, {pending} pending; GRA/GRM; idempotent poll",
        status="ingesting" if pending else "complete",
    )
    print(
        f"done: {downloaded} new, {skipped} already present, "
        f"{pending} awaiting delivery (re-run to pick them up)."
    )


if __name__ == "__main__":
    main()
