"""Loader: DISHA (UN Global Pulse / UNOPS) zero-shot damage assessment -> bronze.

DISHA ("Data Insights for Social and Humanitarian Action", UN Global Pulse,
implemented by UNOPS) delivered an optical zero-shot building-damage assessment for
NW Caracas, powered by Google Earth AI (buildings = Google Open Buildings; damage =
Google DA models). One pre/post image pair; ~38.7k assessed buildings in a ~134 km²
AOI (inside our existing La Guaira coverage). See exploratory checks in the session
notes; harmonization is deferred (this is bronze-only for now — see LICENCE below).

  !!! LICENCE (read before doing ANYTHING past bronze) !!!
  UNOPS-owned, NON-COMMERCIAL use only. The terms explicitly prohibit modifying,
  redistributing, publicly publishing/displaying, or creating derivative works
  WITHOUT PRIOR WRITTEN UNOPS AUTHORIZATION. Serving this in the public damage
  viewer is exactly "public display / derivative work" — do NOT harmonize/serve it
  until that authorization is confirmed. Required attribution: "Buildings Data:
  Powered by Google Earth AI's Open Buildings model; Damage Assessment: DISHA
  powered by Google Earth AI's Damage Assessment models" + the DISHA/UNOPS
  acknowledgment. Testing phase, unvalidated (f1 0.45, AUPRC 0.40, FNR 0.55, n=115).

This lands the delivery in bronze as received: the raw zip (full provenance incl.
the licence PDF) plus its members individually for downstream use.

Run: uv run --group etl python pipelines/ingest_disha.py [path-to.zip]
     (defaults to ~/Downloads/NWCaracas_Analyses.zip)
"""

from __future__ import annotations

import os
import sys
import zipfile

from gie import blobio, ledger
from gie.config import load_settings

SOURCE, ADM0, STAGE = "disha", "VE", "dev"
DEFAULT_ZIP = os.path.expanduser("~/Downloads/NWCaracas_Analyses.zip")

# (zip member, bronze filename, ledger label, ledger detail). Names kept verbatim
# except the transmittal PDF (cleaned for a tidy blob key).
FILES = [
    (
        "NWCaracas_aoi.geojson",
        "NWCaracas_aoi.geojson",
        "AOI polygon",
        "single AOI polygon, ~133.6 km2, NW of Caracas (La Guaira/Catia); EPSG:4326",
    ),
    (
        "NWCaracas_Final_inference_result.csv",
        "NWCaracas_Final_inference_result.csv",
        "DA final inference (the product)",
        "38,652 assessed buildings; building_id (Google Open Buildings id), lon/lat, "
        "score, damaged/damaged_high_precision/damaged_high_recall booleans "
        "(damaged=244; high_precision=high_recall=636 — NB identical, query the provider); "
        "single 'damaged' class -> damage_class 2. The layer to harmonize.",
    ),
    (
        "NWCaracas_footprint_centroids.csv",
        "NWCaracas_footprint_centroids.csv",
        "Google Open Buildings footprint detections",
        "15,159 building centroids + detection confidence (lon/lat/confidence)",
    ),
    (
        "NWCaracas_Zeroshot_Results.csv",
        "NWCaracas_Zeroshot_Results.csv",
        "zero-shot DA scores (raw)",
        "13,469 rows; NB coordinates span beyond the AOI (~-68.17 W) — not AOI-clipped",
    ),
    (
        "NWCaracas_Final_Inference_metrics.csv",
        "NWCaracas_Final_Inference_metrics.csv",
        "model metrics",
        "f1 0.45, AUPRC 0.40, precision/recall 0.45, FNR 0.55, evaluated on n=115",
    ),
    (
        "DISHA - Digital Asset Transmittal [UN].pdf",
        "NWCaracas_transmittal.pdf",
        "transmittal + LICENCE",
        "UNOPS non-commercial; NO public display / derivative / redistribution without "
        "prior written UNOPS authorization; attribution + disclaimer terms.",
    ),
]


def main() -> None:
    zip_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ZIP
    if not os.path.isfile(zip_path):
        raise SystemExit(f"delivery zip not found: {zip_path}")

    settings = load_settings(STAGE)
    fs = blobio.uploader(settings)

    # 1) raw zip as received (full provenance, includes the licence PDF)
    with open(zip_path, "rb") as fh:
        raw = fh.read()
    zblob = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", "NWCaracas_Analyses.zip")
    print(f"uploading raw zip ({len(raw) / 1e6:.1f} MB) -> {zblob}", flush=True)
    blobio.upload(fs, raw, zblob)
    ledger.record(
        SOURCE, "bronze", "raw delivery zip (as received)", zblob,
        "NWCaracas_Analyses.zip — full DISHA delivery incl. licence PDF; UNOPS "
        "non-commercial, no public display/derivative without written authorization.",
        status="ingesting",
    )
    print(f"  bronze <- {zblob}", flush=True)

    # 2) members individually for downstream use
    with zipfile.ZipFile(zip_path) as zf:
        present = set(zf.namelist())
        for member, dest, label, detail in FILES:
            if member not in present:
                raise SystemExit(f"missing zip member: {member}")
            blob = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", dest)
            blobio.upload(fs, zf.read(member), blob)
            ledger.record(SOURCE, "bronze", label, blob, detail, status="ingesting")
            print(f"  bronze <- {blob}", flush=True)

    print("done. (bronze-only — do NOT harmonize/serve until the UNOPS licence is cleared)", flush=True)


if __name__ == "__main__":
    main()
