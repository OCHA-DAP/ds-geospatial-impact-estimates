"""One-time loader: UNEP/OCHA JEU earthquake building-debris assessment (VEN) -> bronze.

A debris *mass* quantification (metric tonnes) for the June 2026 Venezuela
earthquake, by the UNEP/OCHA Joint Environment Unit. Debris is derived from a
Sentinel-1 SAR change-detection analysis (PWTT z-score > 0.4) on a Global
Building Atlas footprint base (with modeled height), with locality damage
products (Copernicus EMS EMSR884, Microsoft AI for Good — used in full for Catia
La Mar / La Guaira / Caraballeda, NASA SAR proxy as fallback) incorporated where
available, and optical (PlanetScope) for visual verification. Debris = built
floor-area x 1 t/m2 (height = stories x 3 m). ~96k buildings, ~17 Mt, across the
affected northern-coast states.

Three geopackages (building level, 350 m hex, 3 km hex; each `id/fid + debris` in
EPSG:32619); PDFs are context maps only (archived under context/, not analysed).
We land the delivery to bronze as received via ocha-stratus (ADR-0003);
idempotency lives in the immutable blob path (ADR-0005).

Silver/gold are DEFERRED pending clarifications requested from the provider that
determine the harmonization: (1) attribution/credit — the source id `unep_debris`
here is provisional; (2) whether other products validated vs were fused into the
result; (3) whether an area-of-analysis polygon (the SAR swath) exists — none is
in the geopackages, so without it the source is detected-only (like HOT_OSM,
ADR-0012) and served as absolute debris mass rather than a coverage-aware rate.

Run: uv run --group etl python pipelines/ingest_debris.py
"""

from __future__ import annotations

import requests

from gie import blobio, events, ledger
from gie.config import load_settings

HDX = "https://data.humdata.org/api/3/action/package_show?id={}"
HDX_SLUG = "building-debris-assessment-venezuela-earthquake-june-2026"
SOURCE = "unep_debris"  # PROVISIONAL — pending the provider's credit answer
ADM0 = "VE"
STAGE = "dev"
EVENT = "20260624-ve-earthquake"  # validated against events.yaml in main()


def _upload(fs, data: bytes, dest: str) -> bool:
    """Upload via the shared reliable helper; skip if already landed at same size."""
    try:
        if fs.get_file_client(dest).get_file_properties().size == len(data):
            return False  # already present at the same size — resumable no-op
    except Exception:
        pass
    blobio.upload(fs, data, dest)
    return True


def main() -> None:
    events.require_event(EVENT)
    settings = load_settings(STAGE)
    resources = requests.get(HDX.format(HDX_SLUG), timeout=60).json()["result"]["resources"]
    fs = blobio.uploader(settings)

    landed = []
    for r in resources:
        fmt, name, url = r.get("format"), r.get("name"), r.get("url")
        if fmt == "Geopackage":
            dest = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", name, event=EVENT)
        elif fmt == "PDF":  # context maps only — archive, not analysed
            dest = settings.blob_path(
                "bronze", f"source={SOURCE}", f"adm0={ADM0}", "context", name, event=EVENT
            )
        else:
            continue
        raw = requests.get(url, timeout=180).content
        did = _upload(fs, raw, dest)
        landed.append((fmt, name, len(raw), dest))
        print(f"  bronze <- {dest}  ({len(raw) / 1e6:.1f} MB){'' if did else '  [already current]'}", flush=True)

    gpkgs = [x for x in landed if x[0] == "Geopackage"]
    pdfs = [x for x in landed if x[0] == "PDF"]
    ledger.record(
        SOURCE,
        "bronze",
        "UNEP/OCHA JEU building-debris assessment — VEN earthquake (HDX)",
        settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", event=EVENT),
        f"{len(gpkgs)} geopackages (debris tonnes: building + 350m + 3km grids, EPSG:32619) "
        f"+ {len(pdfs)} context PDFs; provisional source id; silver/gold deferred pending "
        f"credit / fusion / AOI clarifications",
    )
    print(f"done: {len(gpkgs)} geopackages + {len(pdfs)} context PDFs -> bronze/source={SOURCE}")


if __name__ == "__main__":
    main()
