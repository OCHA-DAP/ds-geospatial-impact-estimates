"""One-time loader: University of Houston building-damage predictions (VEN) -> bronze.

A building-level damage prediction for the June 2026 Venezuela earthquake produced
by a University of Houston group (delivery contact dksingh@cougarnet.uh.edu),
covering eight coastal AOIs (Antimano, Caraballeda, Caracas, Maracay, Moron,
Petare, Santa Cruz, Villa de Cura). Each footprint carries a three-class severity
grade (intact / damaged / destroyed; `cls` 1/2/3 maps 1:1 onto `grade`).

Unlike the detected-only sources (HOT / DISHA / UNEP debris), this delivery
INCLUDES the intact buildings, so an analysed extent is derivable per AOI and the
source supports the full coverage-aware metric set (analysed / fraction /
extrapolated), like Microsoft and Copernicus EMS. The footprint base is
effectively our Overture base (~80% IoU>=0.95 identical), but the features carry
NO id, so harmonization projects damage by centroid-containment onto the Overture
base (the impact_v2 rule, ADR-0015) rather than an id-join.

We land the delivery to bronze as received (ADR-0003, the .geojson verbatim);
idempotency lives in the immutable blob path (ADR-0005). Silver/gold follow in
harmonize_uh.py + harmonize_common.py.

Attribution (provider-supplied): **UH QuakeDamage** — a deep-learning model by Singh
& Hoskere classifying Overture building footprints from pre-/post-event imagery (478K
buildings); https://quakedamage.github.io. The internal source id stays `uh`.
Still to confirm before a prod promote: licence / redistribution terms.

Run: uv run --group etl python pipelines/ingest_uh.py [path-to.geojson]
     (defaults to ~/Downloads/final_maxsev_512.geojson)
"""

from __future__ import annotations

import os
import sys

from azure.storage.blob import ContainerClient

from gie import events, ledger
from gie.config import load_settings

SOURCE = "uh"  # PROVISIONAL — pending the provider's attribution answer
ADM0 = "VE"
STAGE = "dev"
EVENT = "20260624-ve-earthquake"  # validated against events.yaml in main()
DEFAULT_FILE = os.path.expanduser("~/Downloads/final_maxsev_512.geojson")
# Kept verbatim for provenance (the tippecanoe generator command in the delivered
# PMTiles names this exact file); it is the analytical GeoJSON behind the tiles.
DELIVERY_NAME = "final_maxsev_512.geojson"


def main() -> None:
    events.require_event(EVENT)
    src_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FILE
    if not os.path.isfile(src_path):
        raise SystemExit(f"delivery file not found: {src_path}")

    settings = load_settings(STAGE)
    cc = ContainerClient.from_connection_string(
        settings.connection_string(write=True), container_name=settings.container
    )

    blob = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", DELIVERY_NAME, event=EVENT)
    size = os.path.getsize(src_path)
    print(f"uploading {DELIVERY_NAME} ({size / 1e6:.1f} MB) -> {blob}", flush=True)
    with open(src_path, "rb") as f:
        cc.upload_blob(name=blob, data=f, overwrite=True, length=size, max_concurrency=8)

    # preliminary delivery — "ingesting" (not stable/final), matching the other
    # provisional sources (impact_initiatives, osu, unep_debris).
    ledger.record(
        SOURCE,
        "bronze",
        "UH building-damage predictions — VEN earthquake (8 AOIs, graded footprints)",
        blob,
        "478,467 building footprints; grade intact/damaged/destroyed (cls 1/2/3); "
        "EPSG:4326; includes intact -> full metric set; provisional source id, "
        "attribution/licence/method pending provider",
        status="ingesting",
    )
    print(f"  bronze <- {blob}", flush=True)
    print("done.", flush=True)


if __name__ == "__main__":
    main()
