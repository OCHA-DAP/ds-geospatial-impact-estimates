"""Loader: Microsoft merged/deduplicated Venezuela damage dataset -> bronze.

Microsoft AI for Good released a single MERGED, DEDUPLICATED building-damage
dataset spanning all 5 Venezuela AOIs we had been ingesting individually
(caraballeda_east, catia_la_mar, catia_la_mar_east, la_guaira_and_surrounding,
la_guaira_east), plus a single unioned valid-area mask. It deduplicates the AOI
overlaps and reconciles buildings observed by multiple AOIs (carrying
num_observations / uncertainty / sources), so it SUPERSEDES the per-AOI
footprints + masks on the viewer.

Storage: the two files are landed in bronze AS RECEIVED (raw .gpkg / .geojson,
no format change) under .../merged/, via ocha-stratus's container client
(team-standard blob access). The per-AOI bronze (aoi=<name>/) is kept as
historical raw.

CAVEAT — one-off / uncertain cadence (see ADR): we do NOT yet know whether
Microsoft will (a) keep refreshing this merged dataset, or (b) also send
individual AOI tiles not in it. So the per-AOI ingestion path stays available
and this is treated as a manual, re-runnable step rather than an automated feed.

Source files (published 2026-06-28):
  https://geospatialvisualizer.blob.core.windows.net/damage-assessments/\
venezuela_earthquake_2026/results/ALL_AOIS_building_predictions_deduplicated.gpkg
  https://geospatialvisualizer.blob.core.windows.net/damage-assessments/\
venezuela_earthquake_2026/results/valid_area_mask_union.geojson

Run: uv run --group etl python pipelines/ingest_microsoft_merged.py
"""

from __future__ import annotations

import base64
import threading
import time
import urllib.request

import ocha_stratus as stratus
from azure.storage.blob import BlobBlock

from gie import events, ledger
from gie.config import load_settings

SOURCE = "microsoft"
ADM0 = "VE"
STAGE = "dev"
EVENT = "20260624-ve-earthquake"  # validated against events.yaml in main()
BASE_URL = (
    "https://geospatialvisualizer.blob.core.windows.net/"
    "damage-assessments/venezuela_earthquake_2026/results"
)
FILES = [
    "ALL_AOIS_building_predictions_deduplicated.gpkg",
    "valid_area_mask_union.geojson",
]


def _stage(bc, block_id: str, chunk: bytes, tries: int = 6, timeout_s: int = 45) -> None:
    """Stage one block, retried with a per-attempt stall timeout."""
    for attempt in range(tries):
        result: dict = {}

        def _do(result=result):
            try:
                bc.stage_block(block_id=block_id, data=chunk, length=len(chunk))
                result["ok"] = True
            except Exception as e:  # noqa: BLE001 — network write, retry any failure
                result["err"] = e

        th = threading.Thread(target=_do, daemon=True)
        th.start()
        th.join(timeout_s)
        if result.get("ok"):
            return
        reason = "stalled" if th.is_alive() else str(result.get("err", ""))[:40]
        print(f"    block attempt {attempt + 1}/{tries} ({reason}); retrying", flush=True)
        time.sleep(3)
    raise RuntimeError(f"block stage failed after {tries} tries: {block_id}")


def _upload(cc, blob: str, data: bytes, block_size: int = 4 * 1024 * 1024) -> None:
    """Upload via staged blocks. The SDK sends blobs <= 64 MB as a single PUT —
    one long request that stalls and dies on a flaky/slow uplink (the 27 MB file
    failed this way; an 8 MB single PUT squeaked through). Chunking into small
    blocks, each a short request retried individually, gets it through reliably
    (~32s for 27 MB observed)."""
    bc = cc.get_blob_client(blob)
    blocks = []
    for i, off in enumerate(range(0, len(data), block_size)):
        block_id = base64.b64encode(f"{i:06d}".encode()).decode()
        _stage(bc, block_id, data[off : off + block_size])
        blocks.append(BlobBlock(block_id=block_id))
    bc.commit_block_list(blocks)


def main() -> None:
    events.require_event(EVENT)
    settings = load_settings(STAGE)
    cc = stratus.get_container_client(container_name=settings.container, stage=STAGE, write=True)
    first_blob = None
    for name in FILES:
        url = f"{BASE_URL}/{name}"
        print(f"downloading {name} ...", flush=True)
        with urllib.request.urlopen(url, timeout=180) as resp:  # noqa: S310 — trusted MS URL
            data = resp.read()
        blob = settings.blob_path(
            "bronze", f"source={SOURCE}", f"adm0={ADM0}", "merged", name, event=EVENT
        )
        _upload(cc, blob, data)
        print(f"bronze <- {blob} ({len(data) / 1e6:.1f} MB)", flush=True)
        first_blob = first_blob or blob

    ledger.record(
        SOURCE,
        "bronze",
        "Microsoft merged/deduplicated VE damage dataset (all 5 AOIs)",
        first_blob,
        "72,162 deduplicated buildings (8,410 damaged) across 5 AOIs + a single unioned "
        "valid-area mask (no cloud/not-analysed holes), raw .gpkg/.geojson as received; "
        "supersedes the per-AOI ingestion on the viewer (per-AOI bronze kept). Cadence TBD (ADR).",
        status="ingesting",
    )


if __name__ == "__main__":
    main()
