"""One-time loader: IMPACT Initiatives Sentinel-1 SAR damage-proxy raster -> bronze.

IMPACT Initiatives (NGO) produced a preliminary 10 m Sentinel-1 SAR-derived
damage-proxy layer for the Venezuela earthquake, ~8,400 km2 across the most
impacted states (Yaracuy, Carabobo, Aragua, La Guaira, Miranda, Distrito
Capital). It is a *damage proxy / hotspot-and-gap screen*, NOT a confirmed
building-damage product.

Method (unsupervised SAR change detection):
  * Backscatter amplitude change between the first post-event Sentinel-1
    acquisition (2026-06-25) and a one-year pre-event baseline ending 2026-06-23.
  * Intensities noise-filtered -> per-polarisation z-score anomalies -> combined
    across polarisations -> smoothed with a 50 m circular kernel.
  * Pixels with smoothed z-score > 0.7 are provided (lower values masked to
    nodata). 0.7 is an inclusive screening threshold, tested only against the
    Microsoft damage labels in La Guaira; z-score >= 1.0 is a higher-confidence
    (more conservative) cut but may miss smaller damage.

Caveats (must travel downstream — never present as confirmed damage):
  * Experimental / preliminary; relies on a single post-event acquisition.
  * Side-looking SAR: an anomaly can also be debris from damaged buildings, or
    moisture / vegetation / acquisition geometry / other non-damage effects.
  * Intended to flag potential damage hotspots and assessment gaps (including
    optical/cloud gaps), to be triangulated with VHR/optical, Copernicus EMS,
    UNOSAT, Microsoft and validated in the field where possible.

Raster (as received): GeoTIFF, EPSG:4326, ~10 m (8.98e-5 deg), float32 z-scores
(>= 0.7), nodata -3.4e38, ~465 MB, plain (no overviews — not a COG yet).

This loader only lands the raw file in bronze, as received. COG conversion and
projecting the proxy onto the Overture base / admin units are later silver/gold
steps. Streams the file in blocks (it is large) using the write-scoped SAS.

Run: uv run --group etl python pipelines/ingest_impact_sar.py [path-to.tif]
"""

from __future__ import annotations

import os
import sys

from azure.storage.blob import ContainerClient

from gie import ledger
from gie.config import load_settings

SOURCE = "impact_initiatives"
ADM0 = "VE"
STAGE = "dev"
DEFAULT_SRC = os.path.expanduser(
    "~/Downloads/IMPACT_VEN_20260625_Sentinel1_damage_proxy_gt0.70.tif"
)


def main() -> None:
    src_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC
    if not os.path.isfile(src_path):
        raise SystemExit(f"file not found: {src_path}")

    settings = load_settings(STAGE)
    name = os.path.basename(src_path)
    blob = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", name)
    size = os.path.getsize(src_path)

    cc = ContainerClient.from_connection_string(
        settings.connection_string(write=True), container_name=settings.container
    )
    print(f"uploading {name} ({size / 1e6:.0f} MB) -> {blob}", flush=True)
    with open(src_path, "rb") as f:
        cc.upload_blob(name=blob, data=f, overwrite=True, length=size, max_concurrency=8)
    print(f"bronze <- {blob}", flush=True)

    ledger.record(
        SOURCE,
        "bronze",
        "IMPACT Initiatives Sentinel-1 SAR damage proxy (smoothed z-score > 0.7)",
        blob,
        "10 m GeoTIFF, EPSG:4326, float32 z-scores >= 0.7; post-event 2026-06-25 "
        "vs 1-yr pre-event baseline ending 2026-06-23; preliminary hotspot/gap "
        "screen, NOT confirmed damage (method + caveats in module docstring)",
        status="ingesting",
    )


if __name__ == "__main__":
    main()
