"""Loader: Microsoft AI for Good Colombia damage predictions (HDX) -> bronze.

Microsoft ran their building-damage models on post-event VHR imagery for two
cities after the 2026-08-10 M7.4 Colombia earthquake, published as two HDX
datasets (one per city):

  * Pereira — Vantor imagery 2026-08-12 (slug colombia-2026-earthquake-pereira)
  * Cali    — Airbus imagery 2026-08-10 (slug 2026-colombia-earthquake)

Each ships building-level predictions on TWO footprint bases (Overture +
Google), a valid-area mask, and the raw model-prediction raster. The schema
matches the Venezuela Microsoft delivery (damage_pct_0/10/20m, built_pct_0m,
damaged, unknown_pct — cloud cover encoded as unknown_pct). All resources are
landed in bronze exactly as received under aoi=<city>/ (ADR-0005); filenames
carry sensor + acquisition date, so a new delivery is a new immutable blob.
Category "analysis" in the transfer log — this is an ML damage product, in
contrast to the reference/ground-truth sources (CEMS grading, OSM buildings).

Idempotent: already-landed files are skipped; a changed HDX re-upload under
the SAME filename raises instead of silently skipping or overwriting (bronze
is immutable — resolve deliberately). Which footprint base the common model
harmonizes is a silver-step decision, not made here.

Run: uv run --group etl python pipelines/ingest_microsoft_hdx.py
"""

from __future__ import annotations

import json
import posixpath
import tempfile

import ocha_stratus as stratus
import pyogrio
import requests

from gie import blobio, events, ledger
from gie.config import load_settings

HDX = "https://data.humdata.org/api/3/action/package_show?id={}"
DATASETS = {  # aoi label -> HDX dataset slug
    "pereira": "colombia-2026-earthquake-pereira",
    "cali": "2026-colombia-earthquake",
    # Extended Pereira re-run (Vantor 2026-08-13, human-reviewed): 3.3x the
    # original mask but NOT a superset (the west strip stays original-only) —
    # per-building supersession is applied at silver, both deliveries kept.
    "pereira_extended": "colombia-2026-earthquake-pereira-extended",
}
SOURCE = "microsoft"
STAGE = "dev"
EVENT = "20260810-co-earthquake"  # validated against events.yaml in main()
PROVIDER = "Microsoft AI for Good Lab"
LICENCE = "CC-BY (Creative Commons Attribution International)"


def _describe(fname: str, data: bytes) -> str:
    """Short content summary for the ledger, derived from the landed bytes."""
    if fname.endswith(".gpkg"):
        with tempfile.NamedTemporaryFile(suffix=".gpkg") as tmp:
            tmp.write(data)
            tmp.flush()
            info = pyogrio.read_info(tmp.name)
            return f"{fname}: {int(info['features']):,} footprints"
    if fname.endswith(".geojson"):
        n = len(json.loads(data).get("features", []))
        return f"{fname}: {n} feature(s)"
    return f"{fname}: {len(data) / 1e6:.1f} MB"


def ingest_dataset(settings, container, fs, aoi: str, slug: str) -> None:
    resources = requests.get(HDX.format(slug), timeout=60).json()["result"]["resources"]
    if not resources:
        raise RuntimeError(f"HDX dataset {slug} returned no resources")

    summaries, landed = [], 0
    for res in resources:
        fname = posixpath.basename(res["url"])
        blob_name = settings.blob_path(
            "bronze", f"source={SOURCE}", f"aoi={aoi}", fname, event=EVENT
        )
        bc = container.get_blob_client(blob_name)
        if bc.exists():
            declared = res.get("size")
            actual = bc.get_blob_properties().size
            if declared and int(declared) != actual:
                raise RuntimeError(
                    f"{blob_name} exists ({actual:,} B) but HDX now declares "
                    f"{int(declared):,} B for {res['name']} — resource changed under "
                    "the same filename; bronze is immutable, resolve deliberately."
                )
            print(f"  already present: {blob_name}")
            continue

        data = requests.get(res["url"], timeout=600).content
        blobio.upload(fs, data, blob_name)
        landed += 1
        summary = _describe(fname, data)
        summaries.append(summary)
        print(f"  bronze <- {blob_name} ({len(data):,} bytes; {summary})")
        ledger.log_transfer(
            event=EVENT,
            source=SOURCE,
            category="analysis",
            dataset=f"Microsoft AI for Good damage predictions — {aoi.title()} ({res['name']})",
            provider=PROVIDER,
            licence=LICENCE,
            origin_url=res["url"],
            origin_meta={
                "hdx_dataset": slug,
                "hdx_resource_id": res["id"],
                "hdx_last_modified": res.get("last_modified"),
                "summary": summary,
            },
            size_bytes=len(data),
            sha256=ledger.sha256_hex(data),
            blob_path=blob_name,
            stage=STAGE,
        )

    if landed:  # re-runs that land nothing keep the previous (still accurate) entry
        ledger.record(
            SOURCE,
            "bronze",
            f"Microsoft AI for Good CO damage predictions — {aoi.title()} (HDX, CC-BY)",
            settings.blob_path("bronze", f"source={SOURCE}", f"aoi={aoi}", event=EVENT),
            f"{len(resources)} resources as received (per-base prediction gpkgs + "
            "valid-area mask, raster where shipped); "
            + "; ".join(summaries)
            + "; footprint-base choice deferred to silver",
            status="ingesting",
        )
    print(f"{aoi}: {landed} new, {len(resources) - landed} already present.")


def main() -> None:
    events.require_event(EVENT)
    settings = load_settings(STAGE)
    container = stratus.get_container_client(stage=STAGE, container_name=settings.container)
    fs = blobio.uploader(settings)
    for aoi, slug in DATASETS.items():
        ingest_dataset(settings, container, fs, aoi, slug)


if __name__ == "__main__":
    main()
