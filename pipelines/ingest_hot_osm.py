"""One-time loader: HOT fAIr earthquake building-damage points (VEN).

HOTOSM's fAIr platform (fair.hotosm.org) ran an AI damage-assessment model on
post-event WorldView-3 imagery (0.34 m, acquired 2026-06-26, via OpenAerialMap)
for the M7.5 Venezuela earthquake. The product is a small set of points over
La Guaira, each flagging a possibly-damaged building with a class
(minor-damage / major-damage / destroyed) and a confidence; the `description`
also carries per-class probabilities. This is a fourth damage source alongside
Microsoft, Copernicus EMS, and IMPACT SAR.

Source: HDX, CC-BY (dataset slug below). We land the GeoJSON to bronze exactly
as received via ocha-stratus (ADR-0003); idempotency lives in the immutable
blob path (ADR-0005). Silver/gold are deferred: there is no published analysed
AOI for the damage model (the imagery footprint is ~33x the damaged extent), so
for now this source is detected-only — see the v1 decision in the HOT_OSM notes.

Run: uv run --group etl python pipelines/ingest_hot_osm.py
"""

from __future__ import annotations

import json

import ocha_stratus as stratus
import requests

from gie import ledger
from gie.config import load_settings

HDX = "https://data.humdata.org/api/3/action/package_show?id={}"
# Stable HDX slug, not a download URL: _resource_url() resolves the current
# GeoJSON URL at runtime, so a HOT re-upload is picked up automatically.
HDX_SLUG = "venezuela-m-7-5-earthquake-building-damage-assessment"
RESOURCE = "fair_damage_points.geojson"
SOURCE = "hot_osm"
ADM0 = "VE"
STAGE = "dev"


def _resource_url(slug: str, fmt: str = "GeoJSON") -> str:
    """First resource of format `fmt` on an HDX dataset."""
    rs = requests.get(HDX.format(slug), timeout=60).json()["result"]["resources"]
    return next(r["url"] for r in rs if r["format"] == fmt)


def main() -> None:
    settings = load_settings(STAGE)

    raw = requests.get(_resource_url(HDX_SLUG), timeout=60).content
    bronze = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", RESOURCE)
    stratus.upload_blob_data(raw, bronze, stage=STAGE, container_name=settings.container)

    # Light summary from the raw GeoJSON (stdlib only — no normalization here).
    feats = json.loads(raw).get("features", [])
    classes: dict[str, int] = {}
    for f in feats:
        cls = (f.get("properties") or {}).get("damage", "unknown")
        classes[cls] = classes.get(cls, 0) + 1
    breakdown = ", ".join(f"{k}={v}" for k, v in sorted(classes.items()))
    print(f"bronze <- {bronze}  ({len(feats):,} damage points; {breakdown})")

    ledger.record(
        SOURCE,
        "bronze",
        "HOT fAIr earthquake building-damage points — La Guaira (HDX, CC-BY)",
        bronze,
        f"{len(feats):,} points; classes: {breakdown}; EPSG:4326; detected-only (no analysed AOI)",
    )


if __name__ == "__main__":
    main()
