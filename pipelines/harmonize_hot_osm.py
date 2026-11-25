"""Normalize HOT fAIr damage points (bronze GeoJSON) -> silver.

Reads the bronze damage points and standardises them to the project's damage
model. fAIr's three classes map onto the Copernicus damage_class scale used by
the common model, so cross-source comparison reads in the same units:
    minor-damage -> class 1 ("Possibly damaged")
    major-damage -> class 2 ("Damaged")
    destroyed    -> class 3 ("Destroyed")
We keep the source's own `confidence` and the per-class probabilities parsed out
of the point's `description`, plus the native fAIr label for provenance.

Output: damage_points.parquet — one row per fAIr damage point. The points are
NOT snapped to the Overture base here; like CEMS, that join happens in
harmonize_common (the only place that scans the base). There is no analysed
extent: fAIr published no AOI for the damage model, so this source is
detected-only in the common model (see the HOT_OSM notes / ingest_hot_osm.py).

Run: uv run --group etl python pipelines/harmonize_hot_osm.py
"""

from __future__ import annotations

import re
import tempfile

import geopandas as gpd
import ocha_stratus as stratus

from gie import events, ledger
from gie.config import load_settings

SOURCE = "hot_osm"
ADM0 = "VE"
STAGE = "dev"
EVENT = "20260624-ve-earthquake"  # validated against events.yaml in main()
RESOURCE = "fair_damage_points.geojson"

# fAIr class -> (common-model damage_class, CEMS-aligned grade label)
CLASS = {
    "minor-damage": (1, "Possibly damaged"),
    "major-damage": (2, "Damaged"),
    "destroyed": (3, "Destroyed"),
}
# "p(minor/major/destroyed): 0.30/0.50/0.10" in the point description
_PROBS = re.compile(r"p\(minor/major/destroyed\):\s*([\d.]+)/([\d.]+)/([\d.]+)")


def main() -> None:
    events.require_event(EVENT)
    settings = load_settings(STAGE)

    bronze = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", RESOURCE, event=EVENT)
    raw = stratus.load_blob_data(bronze, stage=STAGE, container_name=settings.container)
    with tempfile.NamedTemporaryFile(suffix=".geojson") as tf:
        tf.write(raw)
        tf.flush()
        gdf = gpd.read_file(tf.name).to_crs(4326)

    gdf["fair_damage"] = gdf["damage"]
    gdf["damage_class"] = gdf["damage"].map(lambda d: CLASS[d][0])
    gdf["ems_grade"] = gdf["damage"].map(lambda d: CLASS[d][1])

    probs = gdf["description"].str.extract(_PROBS).astype(float)
    gdf["p_minor"], gdf["p_major"], gdf["p_destroyed"] = probs[0], probs[1], probs[2]

    out = gdf[
        [
            "damage_class", "ems_grade", "fair_damage", "confidence",
            "p_minor", "p_major", "p_destroyed", "geometry",
        ]
    ]
    silver = settings.blob_path(
        "silver", f"source={SOURCE}", f"adm0={ADM0}", "damage_points.parquet", event=EVENT
    )
    stratus.upload_parquet_to_blob(
        out, silver, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    by_grade = ", ".join(
        f"{g}={int((out['damage_class'] == c).sum())}"
        for c, g in sorted((c, g) for c, g in {v[0]: v[1] for v in CLASS.values()}.items())
    )
    print(f"silver <- {silver} ({len(out):,} damage points; {by_grade})", flush=True)

    ledger.record(
        SOURCE,
        "silver",
        "HOT fAIr damage points normalized to CEMS damage classes",
        silver,
        f"{len(out):,} points; {by_grade}; detected-only (no analysed AOI); EPSG:4326",
    )


if __name__ == "__main__":
    main()
