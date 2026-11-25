"""Idempotent loader: Copernicus EMS Rapid Mapping damage products -> bronze.

Registry-driven, one event per run: ``--event <event_id>`` names the event to
poll and the activation code comes from that event's
``external_ids.cems_activation`` in events.yaml (ADR-0027 — the registry, not
the CLI, says which activation belongs to which event; the flag only picks
WHICH registered event this run refreshes, so pulling Colombia never touches
the Venezuela tree). Delivered product zips land in bronze via the ocha-lens
`cems` datasource. CEMS
delivers products piecemeal over the life of an open activation, with version
and monitoring updates, so this loader is built to be re-run on any cadence:

  * each product version lands at a unique, immutable, version-encoded path;
  * already-present products are skipped (no re-download, no overwrite);
  * each poll writes a timestamped manifest snapshot of the activation state;
  * each file actually landed is logged to data_transfers.jsonl (category
    "reference" — CEMS grading is expert visual interpretation, ground truth
    for the ML-derived sources).

No central ledger DB yet — idempotency lives in the blob layout. See
docs/decisions/0005 (and 0001 for where this source fits the harmonization
model). Harmonizing the damage-grade polygons onto the exposure base / H3 grid
is a later (silver/gold) step; this only lands raw bronze.

Run: uv run --group etl python pipelines/ingest_cems.py --event 20260810-co-earthquake
"""

from __future__ import annotations

import argparse
import posixpath

import ocha_lens as lens
import ocha_stratus as stratus
import pandas as pd

from gie import blobio, events, ledger
from gie.config import load_settings

SOURCE = "copernicus_ems"
STAGE = "dev"
PROVIDER = "Copernicus Emergency Management Service (rapid mapping)"
LICENCE = "CEMS free re-use with attribution (© European Union)"


def _product_blob(settings, activation: str, event_id: str, row, fname: str) -> str:
    """Immutable, version-encoded bronze key for one product version."""
    return settings.blob_path(
        "bronze",
        f"source={SOURCE}",
        f"code={activation}",
        f"aoi={int(row['aoi_number']):02d}",
        f"product_type={row['product_type']}",
        f"v{int(row['version_number'])}_m{int(row['monitoring_number'])}",
        fname,
        event=event_id,
    )


def ingest_activation(settings, container, fs, ev: events.Event, activation: str) -> None:
    prods = lens.cems.get_products(activation)

    # Immutable manifest snapshot, keyed by the latest product delivery time so a
    # re-poll with no new deliveries reuses the same snapshot name.
    latest = prods["delivery_time"].max()
    snap = (
        pd.to_datetime(latest).strftime("%Y%m%dT%H%M%S") if pd.notna(latest) else "pending"
    )
    manifest = settings.blob_path(
        "bronze", f"source={SOURCE}", f"code={activation}", f"products_{snap}.parquet",
        event=ev.event_id,
    )
    stratus.upload_parquet_to_blob(
        prods, manifest, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"manifest <- {manifest} ({len(prods)} products)")

    delivered = prods[prods["download_url"].notna()]
    undelivered = prods[prods["download_url"].isna()]
    # CEMS closes a product it will never publish with status_code "N" (not
    # delivered — e.g. EMSR916's Western Colombia GRM: "remote sensing
    # limitations"). That is a TERMINAL state, not a pending one: counting it
    # as pending would leave the ledger saying "re-run to pick it up" forever.
    closed = undelivered[undelivered["status_code"] == "N"]
    downloaded = skipped = 0
    for _, row in delivered.iterrows():
        fname = posixpath.basename(str(row["download_url"]))
        blob_name = _product_blob(settings, activation, ev.event_id, row, fname)
        if container.get_blob_client(blob_name).exists():
            skipped += 1
            continue
        data = lens.cems.download_product(row, dest=None)
        blobio.upload(fs, data, blob_name)
        downloaded += 1
        print(f"  bronze <- {blob_name} ({len(data):,} bytes)")
        ledger.log_transfer(
            event=ev.event_id,
            source=SOURCE,
            category="reference",
            dataset=f"Copernicus EMS {activation} {row['product_type']} product",
            provider=PROVIDER,
            licence=LICENCE,
            origin_url=str(row["download_url"]),
            origin_meta={
                "activation": activation,
                "aoi_number": int(row["aoi_number"]),
                "aoi_name": str(row["aoi_name"]),
                "product_type": str(row["product_type"]),
                "version_number": int(row["version_number"]),
                "monitoring_number": int(row["monitoring_number"]),
                "delivery_time": str(row["delivery_time"]),
            },
            size_bytes=len(data),
            sha256=ledger.sha256_hex(data),
            blob_path=blob_name,
            stage=STAGE,
        )

    pending = len(undelivered) - len(closed)
    closed_txt = (
        " closed without delivery: "
        + ", ".join(f"{r.aoi_name} {r.product_type}" for r in closed.itertuples())
        + ";"
        if len(closed)
        else ""
    )
    ledger.record(
        source=SOURCE,
        layer="bronze",
        dataset=f"Copernicus EMS {activation} — {ev.name} damage products",
        path=settings.blob_path(
            "bronze", f"source={SOURCE}", f"code={activation}", event=ev.event_id
        ),
        detail=(
            f"{len(delivered)} delivered, {pending} pending;{closed_txt} "
            "reference/ground-truth (expert grading); idempotent poll"
        ),
        status="ingesting" if pending else "complete",
    )
    print(
        f"{activation} ({ev.event_id}): {downloaded} new, {skipped} already present, "
        f"{pending} awaiting delivery, {len(closed)} closed without delivery."
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--event",
        required=True,
        help="event_id from events.yaml; its external_ids.cems_activation is polled",
    )
    args = parser.parse_args(argv)

    ev = events.get_event(args.event)  # fails loudly on an unregistered event
    activation = ev.external_ids.get("cems_activation")
    if not activation:
        raise RuntimeError(
            f"event {ev.event_id!r} has no external_ids.cems_activation in "
            "events.yaml — register the activation code before polling."
        )

    settings = load_settings(STAGE)
    container = stratus.get_container_client(stage=STAGE, container_name=settings.container)
    fs = blobio.uploader(settings)  # reliable chunked+concurrent upload for the product zips
    ingest_activation(settings, container, fs, ev, activation)


if __name__ == "__main__":
    main()
