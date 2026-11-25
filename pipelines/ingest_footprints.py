"""One-time loader: Microsoft building-damage footprints + valid-area masks.

Each Venezuela-earthquake AOI on HDX (Catia La Mar, La Guaira East, Caraballeda
East) ships a GeoPackage of per-building damage predictions (binary `damaged`
+ damage_pct) and a `valid_area_mask` GeoJSON — Microsoft's actual analysis
extent (its coverage footprint, the analogue of CEMS's imageFootprint).

We concatenate the footprints to silver, and the masks to a silver analysed
extent that the common model uses as MS coverage (replacing the old bbox
approximation, so MS gets honest coverage % and extrapolation like CEMS).
Source: HDX, CC-BY. Uses ocha-stratus for the one-time write (ADR-0003).

Run: uv run --group etl python pipelines/ingest_footprints.py
"""

from __future__ import annotations

import tempfile
import urllib.request
from pathlib import Path

import geopandas as gpd
import ocha_stratus as stratus
import pandas as pd
import requests

from gie import events, ledger
from gie.config import load_settings

HDX = "https://data.humdata.org/api/3/action/package_show?id={}"
# HDX dataset slug -> short AOI name. We store stable slugs, not download URLs;
# _resources() resolves the current .gpkg/.geojson URLs from HDX at runtime, so a
# Microsoft re-upload is picked up automatically. New AOIs: add the slug here.
MS_AOIS = {
    "venezuela-earthquakes-catia-la-mar": "catia_la_mar",
    "venezuela-earthquakes-building-damage-assessment-in-catia-la-mar-east": "catia_la_mar_east",
    "venezuela-earthquakes-building-damage-assessment-in-la-guaira": "la_guaira_east",
    "building-damage-assessment-la-guaira-coastline-building-damage-assessment": "la_guaira_surrounding",  # noqa: E501
    "venezuela-earthquakes-building-damage-assessment-in-caraballeda": "caraballeda_east",
}
# AOIs superseded by a newer assessment that spatially encloses them. They stay
# in bronze + silver for provenance but are flagged `superseded`, so the gold
# (and the front-end map/statistics) uses only the latest. la_guaira_surrounding
# encloses la_guaira_east.
SUPERSEDED = {"la_guaira_east"}
SOURCE = "microsoft"
ADM0 = "VE"
STAGE = "dev"
EVENT = "20260624-ve-earthquake"  # validated against events.yaml in main()


def _resources(slug: str) -> tuple[str, str]:
    """(gpkg_url, valid_area_mask_url) for an HDX dataset."""
    rs = requests.get(HDX.format(slug), timeout=60).json()["result"]["resources"]
    gpkg = next(r["url"] for r in rs if r["format"] == "Geopackage")
    mask = next(r["url"] for r in rs if r["format"] == "GeoJSON")
    return gpkg, mask


def main() -> None:
    events.require_event(EVENT)
    settings = load_settings(STAGE)
    foot_parts, mask_parts = [], []

    for slug, aoi in MS_AOIS.items():
        gpkg_url, mask_url = _resources(slug)
        with tempfile.TemporaryDirectory() as tmp:
            gp = Path(tmp) / "f.gpkg"
            mk = Path(tmp) / "m.geojson"
            urllib.request.urlretrieve(gpkg_url, gp)  # noqa: S310 (trusted HDX)
            urllib.request.urlretrieve(mask_url, mk)  # noqa: S310

            for raw, name in ((gp, "footprints.gpkg"), (mk, "valid_area_mask.geojson")):
                bronze = settings.blob_path(
                    "bronze", f"source={SOURCE}", f"adm0={ADM0}", f"aoi={aoi}", name, event=EVENT
                )
                stratus.upload_blob_data(
                    raw.read_bytes(), bronze, stage=STAGE, container_name=settings.container
                )

            g = gpd.read_file(gp).to_crs(4326)
            if "damage_pct_10m" not in g.columns:
                g["damage_pct_10m"] = float("nan")
            g["aoi"] = aoi
            g["superseded"] = aoi in SUPERSEDED
            foot_parts.append(g[["damaged", "damage_pct_10m", "aoi", "superseded", "geometry"]])

            m = gpd.read_file(mk).to_crs(4326)
            m["aoi"] = aoi
            m["superseded"] = aoi in SUPERSEDED
            mask_parts.append(m[["aoi", "superseded", "geometry"]])
        tag = " (superseded — excluded from gold)" if aoi in SUPERSEDED else ""
        print(
            f"  {aoi}: {len(g):,} footprints ({int(g['damaged'].sum())} damaged){tag}",
            flush=True,
        )

    foot = gpd.GeoDataFrame(pd.concat(foot_parts, ignore_index=True), crs="EPSG:4326")
    silver = settings.blob_path(
        "silver", f"source={SOURCE}", f"adm0={ADM0}", "footprints.parquet", event=EVENT
    )
    stratus.upload_parquet_to_blob(
        foot, silver, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"silver <- {silver} ({len(foot):,} footprints across {len(MS_AOIS)} AOIs)")

    masks = gpd.GeoDataFrame(pd.concat(mask_parts, ignore_index=True), crs="EPSG:4326")
    msilver = settings.blob_path(
        "silver", f"source={SOURCE}", f"adm0={ADM0}", "analysed_extent.parquet", event=EVENT
    )
    stratus.upload_parquet_to_blob(
        masks, msilver, stage=STAGE, container_name=settings.container, compression="zstd"
    )
    print(f"silver <- {msilver} ({len(masks)} valid-area masks)")

    ledger.record(
        SOURCE,
        "silver",
        "Building footprints — Catia La Mar + La Guaira + Caraballeda (HDX, CC-BY)",
        silver,
        f"{len(foot):,} footprints; {len(MS_AOIS)} AOIs; binary damaged + valid-area masks",
    )


if __name__ == "__main__":
    main()
