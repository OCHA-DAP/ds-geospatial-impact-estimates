"""Idempotent loader: OSU Sentinel-1 building-damage delivery -> bronze.

Corey Scher & Jamon Van Den Hoek (Oregon State University) produced a preliminary
Sentinel-1 building-damage assessment for the 24 June 2026 Venezuela earthquake
(USGS us6000t7zp; Copernicus EMS activation EMSR884).

Method (Sentinel-1 *coherent change detection* — distinct from the IMPACT
amplitude-z-score proxy): radar coherence loss between post-event acquisitions and
a 1-year pre-event reference stack; a building (Overture footprint) is flagged when
>= 50% of its footprint falls on the coherence-loss map; the threshold is
calibrated against the USGS ShakeMap so the false-alarm rate stays <= 1% in
lightly-shaken areas. Preliminary, unvalidated — an indicator, not a census.

Two deliveries; `--version` selects which lands (bronze keeps both — the filenames
carry the version, so v1 never overwrites v0):
  * v0 (25 Jun, NASA Disasters / Box): local package dir; damaged-only gpkg with a
    continuous `damage_probability`; ~58,870 flagged; ~75% of dry land imaged.
  * v1 (01 Jul, HDX): fetched from the published HDX resource URLs. Expanded
    coverage (MMI>=VI zone now 100%; monitored footprints 2.13M -> 2.70M);
    ~69,431 flagged. One gpkg now carries a CATEGORICAL `damage_confidence`
    (possible/probable/high_confidence) over damaged AND non-damaged rows.

Downstream keying is unchanged: each building carries its `overture_id`, so
harmonization is an id-join onto our Overture base plus the analyzed-area polygon
as the coverage extent (harmonize_osu.py + harmonize_common.py). See ADR-0009.

Run: uv run --group etl python pipelines/ingest_osu.py [--version v0|v1] [package-dir]
     (v0 package-dir defaults to ~/Downloads/S1_Damage_Prelim_EMSR884; v1 ignores it)
"""

from __future__ import annotations

import argparse
import os
import urllib.request

from azure.storage.blob import ContainerClient

from gie import ledger
from gie.config import load_settings

SOURCE = "osu"
ADM0 = "VE"
STAGE = "dev"
DEFAULT_DIR = os.path.expanduser("~/Downloads/S1_Damage_Prelim_EMSR884")

_HDX = "https://data.humdata.org/dataset/222eef8e-c4fe-46b2-a3d5-bb4b90cf872b/resource"

# v0: (filename, ledger dataset label, ledger detail) — read from a local dir.
FILES_V0 = [
    (
        "EMSR884_damage_20260625_v0_damaged.gpkg",
        "damaged buildings (quick-look)",
        "58,870 Overture footprints flagged likely damaged/destroyed; fields "
        "overture_id, damage(=1), damage_probability, coverage_fraction(>=0.5), label",
    ),
    (
        "EMSR884_analyzed_area_20260625_v0.gpkg",
        "analyzed-area outline",
        "single polygon of usable S1 coverage (~75% of dry land imaged); the "
        "coverage extent for the common model (analog of CEMS analysed_extent)",
    ),
    (
        "EMSR884_damage_20260625_v0.gpkg",
        "all assessed structures (full)",
        "every Overture footprint in the assessed area (~2.1M) with damage 0/1, "
        "within_coverage, coverage_fraction, damage_probability; archived for "
        "provenance — downstream derives 'analysed' from the analyzed-area polygon",
    ),
    (
        "README.md",
        "delivery README",
        "OSU/NASA delivery notes: method, calibration, coverage, citation, caveats",
    ),
]

# v1: (filename, HDX download URL, ledger dataset label, ledger detail) — fetched.
FILES_V1 = [
    (
        "EMSR884_damage_confidence_20260701_v1.gpkg",
        f"{_HDX}/4466da86-384f-488f-812a-ae69f36a3582/download/emsr884_damage_confidence_20260701_v1.gpkg",
        "damaged + candidate buildings (confidence-tiered)",
        "123,633 Overture footprints; fields overture_id, damage(0/1), "
        "damage_confidence(possible/probable/high_confidence); damage==1 = 69,431 likely damaged",
    ),
    (
        "EMSR884_analyzed_area_20260701_v1.gpkg",
        f"{_HDX}/806e2d14-f9b4-4f8a-b341-f3b6810b1746/download/emsr884_analyzed_area_20260701_v1.gpkg",
        "analyzed-area outline",
        "single polygon of usable S1 coverage (MMI>=VI zone now 100% imaged); the "
        "coverage extent for the common model",
    ),
    (
        "EMSR884_adm2_damage_pct_20260701_v1.gpkg",
        f"{_HDX}/89e21404-89b4-48a5-b413-257fa1ea463a/download/emsr884_adm2_damage_pct_20260701_v1.gpkg",
        "adm2 damage summary (provider aggregates)",
        "90 adm2 units with n_total/n_assessed/n_damaged/pct_damaged/assessed_fraction; "
        "OSU's own admin rollup — a cross-check for our common-model facts, not a pipeline source",
    ),
    (
        "EMSR884_damage_20260701_v1_README.pdf",
        f"{_HDX}/4595f742-3fb4-435c-9410-d6ee58abc2eb/download/emsr884_damage_20260701_v1_readme.pdf",
        "delivery README",
        "OSU/NASA v1 delivery notes: method, calibration, coverage expansion, citation, caveats",
    ),
]


def _upload(cc, settings, name: str, data: bytes) -> str:
    blob = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", name)
    cc.upload_blob(name=blob, data=data, overwrite=True, length=len(data), max_concurrency=8)
    return blob


def _ingest_v0(cc, settings, pkg_dir: str) -> None:
    if not os.path.isdir(pkg_dir):
        raise SystemExit(f"package dir not found: {pkg_dir}")
    for name, dataset, detail in FILES_V0:
        src_path = os.path.join(pkg_dir, name)
        if not os.path.isfile(src_path):
            raise SystemExit(f"missing delivery file: {src_path}")
        with open(src_path, "rb") as f:
            data = f.read()
        print(f"uploading {name} ({len(data) / 1e6:.1f} MB, local) -> bronze", flush=True)
        blob = _upload(cc, settings, name, data)
        ledger.record(SOURCE, "bronze", dataset, blob, detail, status="ingesting")
        print(f"  bronze <- {blob}", flush=True)


def _ingest_v1(cc, settings) -> None:
    for name, url, dataset, detail in FILES_V1:
        print(f"fetching {name} from HDX ...", flush=True)
        with urllib.request.urlopen(url) as resp:  # noqa: S310 (trusted HDX host)
            data = resp.read()
        print(f"  uploading {name} ({len(data) / 1e6:.1f} MB) -> bronze", flush=True)
        blob = _upload(cc, settings, name, data)
        ledger.record(SOURCE, "bronze", dataset, blob, detail, status="ingesting")
        print(f"  bronze <- {blob}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", choices=["v0", "v1"], default="v1")
    ap.add_argument("pkg_dir", nargs="?", default=DEFAULT_DIR, help="v0 only: local package dir")
    args = ap.parse_args()

    settings = load_settings(STAGE)
    cc = ContainerClient.from_connection_string(
        settings.connection_string(write=True), container_name=settings.container
    )

    if args.version == "v0":
        _ingest_v0(cc, settings, args.pkg_dir)
    else:
        _ingest_v1(cc, settings)

    print("done.", flush=True)


if __name__ == "__main__":
    main()
