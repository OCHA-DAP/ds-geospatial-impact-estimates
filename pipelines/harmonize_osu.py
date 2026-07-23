"""Project the OSU Sentinel-1 coherence damage assessment onto the Overture base -> silver.

See ADR-0009 for the design decisions (id-join over geometry, damage_class
mapping, analyzed-area polygon as extent, damaged-only per-building stopgap) and
its v1 amendment (the categorical confidence schema + versioned silver).

OSU (Corey Scher & Jamon Van Den Hoek, Oregon State University) delivered
building-level damage already keyed to Overture footprints (`overture_id`), so —
unlike the IMPACT raster proxy (ingest/harmonize_impact_sar) — there is no raster
sampling: the damaged set is a straight id-join onto our Overture base, and the
analyzed-area polygon is the coverage extent.

Two deliveries exist and BOTH are materialised, side by side, so they can be
compared (coverage/damaged-set diffs); `--version` selects which one this run
writes. Downstream (harmonize_common, build_platinum) reads exactly one via
`gie.config.OSU_PUBLISHED_VERSION`.

  * v0 (25 Jun 2026): a pre-filtered damaged-only gpkg with a continuous
    `damage_probability`; ~58,870 damaged; ~75% of dry land imaged.
  * v1 (01 Jul 2026): expanded coverage (MMI>=VI zone now 100%; monitored
    footprints 2.13M -> 2.70M). The delivery bundles damaged AND non-damaged rows
    with a CATEGORICAL `damage_confidence` (possible / probable / high_confidence).
    `damage==1` (probable + high_confidence) = 69,431 = OSU's published headline;
    `possible` (54,202, damage==0) is a lower-confidence candidate tier we keep in
    silver for analysis but do NOT count as damaged.

Silver outputs per version (under version=<v>/):
  * building_damage.parquet — one row per OSU-DAMAGED building (id, damage_class,
    the confidence signal, ems_grade). No geometry: `id` joins onto the Overture
    base. This is the damaged contract the common model consumes (every row = damaged).
  * damage_footprints.parquet — the same damaged buildings WITH footprint geometry,
    for the client's native PMTiles view.
  * analysed_extent.parquet — the analyzed-area polygon (the coverage extent).
  * assessed_confidence.parquet — (v1 only) the FULL tiered set incl `possible`,
    the "carry the classes as far as possible" home for downstream analysis.

Confidence is CERTAINTY, not severity: every damaged building stays damage_class 2
(ADR-0009); the tier rides along as the confidence signal (replacing v0's
`damage_probability`), never promoting high_confidence to Destroyed.

Run: uv run --group etl python pipelines/harmonize_osu.py [--version v0|v1]
"""

from __future__ import annotations

import argparse
import os
import tempfile

import geopandas as gpd
import ocha_stratus as stratus

from gie import ledger
from gie.config import load_settings

SOURCE = "osu"
ADM0 = "VE"
STAGE = "dev"

# Bronze gpkg filenames per delivery (bronze is not version-partitioned — the
# filenames themselves carry the version, so v1 never overwrites v0).
DAMAGED_GPKG_V0 = "EMSR884_damage_20260625_v0_damaged.gpkg"
AOI_GPKG_V0 = "EMSR884_analyzed_area_20260625_v0.gpkg"
CONFIDENCE_GPKG_V1 = "EMSR884_damage_confidence_20260701_v1.gpkg"
AOI_GPKG_V1 = "EMSR884_analyzed_area_20260701_v1.gpkg"


def _read_gpkg(settings, name, columns=None):
    """Pull a bronze GeoPackage to a temp file and read it (the azure driver does
    not read .gpkg straight from blob)."""
    bpath = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", name)
    raw = stratus.load_blob_data(bpath, stage=STAGE, container_name=settings.container)
    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tf:
        tf.write(raw)
        tmp = tf.name
    try:
        return gpd.read_file(tmp, columns=columns)
    finally:
        os.unlink(tmp)


def _normalize_v0(settings) -> dict:
    """v0 (25 Jun): damaged-only gpkg with a continuous ``damage_probability``.

    Preserved verbatim from the original single-version harmoniser — the only
    change vs. the pre-versioning code is that main() now writes these frames under
    the version=v0/ silver partition.
    """
    dmg = _read_gpkg(settings, DAMAGED_GPKG_V0, columns=["overture_id", "damage_probability"])

    out = dmg.rename(columns={"overture_id": "id"})[["id", "damage_probability"]].copy()
    out["damage_class"] = 2  # single "likely damaged/destroyed" class -> Damaged
    out["ems_grade"] = "Damaged"

    foot = dmg.rename(columns={"overture_id": "id"})[["id", "damage_probability", "geometry"]].to_crs(4326)
    foot["damage_class"] = 2
    foot["ems_grade"] = "Damaged"

    aoi = _read_gpkg(settings, AOI_GPKG_V0)[["geometry"]].copy()
    aoi["source"] = SOURCE

    return {
        "building_damage": out,
        "damage_footprints": foot,
        "analysed_extent": aoi,
    }


def _normalize_v1(settings) -> dict:
    """v1 (01 Jul): one gpkg bundling damaged + non-damaged rows with a CATEGORICAL
    ``damage_confidence`` (possible / probable / high_confidence).

    The damaged contract is ``damage==1`` (probable + high_confidence = 69,431,
    OSU's headline). ``possible`` (damage==0) is kept only in assessed_confidence
    for analysis — never in the damaged files the common model / native view read.
    """
    conf = _read_gpkg(settings, CONFIDENCE_GPKG_V1).rename(columns={"overture_id": "id"}).to_crs(4326)

    # Full tiered set (incl `possible`) — the analysis home; carry the classes as far as possible.
    assessed = conf[["id", "damage", "damage_confidence", "geometry"]].copy()

    dmg = conf[conf["damage"] == 1].copy()  # probable + high_confidence
    out = dmg[["id", "damage_confidence"]].copy()
    out["damage_class"] = 2  # certainty tier, not severity -> single Damaged class (ADR-0009)
    out["ems_grade"] = "Damaged"

    foot = dmg[["id", "damage_confidence", "geometry"]].copy()
    foot["damage_class"] = 2
    foot["ems_grade"] = "Damaged"

    aoi = _read_gpkg(settings, AOI_GPKG_V1)[["geometry"]].copy()
    aoi["source"] = SOURCE

    return {
        "building_damage": out,
        "damage_footprints": foot,
        "analysed_extent": aoi,
        "assessed_confidence": assessed,
    }


NORMALIZERS = {"v0": _normalize_v0, "v1": _normalize_v1}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", choices=list(NORMALIZERS), default="v1")
    version = ap.parse_args().version

    settings = load_settings(STAGE)
    frames = NORMALIZERS[version](settings)

    for name, frame in frames.items():
        path = settings.blob_path(
            "silver", f"source={SOURCE}", f"adm0={ADM0}", f"version={version}", f"{name}.parquet"
        )
        stratus.upload_parquet_to_blob(
            frame, path, stage=STAGE, container_name=settings.container, compression="zstd"
        )
        print(f"silver <- {path} ({len(frame):,} rows)", flush=True)

    n_dmg = len(frames["building_damage"])
    ledger.record(
        SOURCE,
        "silver",
        f"OSU S1 coherence damage ({version}) joined to Overture (id-keyed) + analyzed-area extent",
        settings.blob_path("silver", f"source={SOURCE}", f"adm0={ADM0}", f"version={version}", "building_damage.parquet"),
        f"{n_dmg:,} damaged buildings (damage_class 2); analysed extent = analyzed-area polygon; "
        f"confidence signal = {'damage_confidence tier' if version == 'v1' else 'damage_probability'}",
        status="ingesting",
    )


if __name__ == "__main__":
    main()
