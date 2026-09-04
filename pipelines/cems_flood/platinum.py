"""Platinum: the published serving layer for the flood label corpus — a
versioned Portolan catalog (STAC + GeoParquet + PMTiles) consumed by the
pages/labels viewer via the token issuer.

Collections:
  labels        one row per label set; flood extent geometry SIMPLIFIED for
                display (full fidelity stays in gold, which the academic
                partner receives directly); tile attrs: code, aoi, label_day,
                acq_start, sensor, acq_method, area_km2. PMTiles derivative.
  valid-masks   the analysed-area masks, heavily simplified. PMTiles.
  label-index   label_index.parquet verbatim (no geometry; the viewer reads
                it client-side with hyparquet).

Unlike the event viewer's platinum (ADR-0009: history not retained), this
catalog's versions.json IS a record — the corpus gets cited. Update via
`portolan sync`; never hand-delete the remote directory.

Prereqs: gold pulled locally (see --src), portolan-cli[pmtiles], tippecanoe.
Run:  uv run --group etl --group api python pipelines/cems_flood/platinum.py [--push]
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

import common
import geopandas as gpd
import pandas as pd

DEST = "az://global/copernicus_ems/flood/platinum"
SIMPLIFY_FLOOD = 1e-4  # ~10 m: display-grade, keeps shoreline character
SIMPLIFY_MASK = 5e-4


def _portolan(args: list[str], cwd: Path, env: dict | None = None) -> None:
    r = subprocess.run(
        ["portolan", *args],
        cwd=str(cwd),
        input="",
        text=True,
        env={**os.environ, **(env or {})},
    )
    if r.returncode != 0:
        raise RuntimeError(f"portolan {' '.join(args)} failed ({r.returncode})")


def build_collections(src: Path, cat: Path) -> None:
    idx = pd.read_parquet(src / "label_index.parquet")
    # full interval key: (code, aoi, acq_start) alone collides where a
    # date-precision interval and a window interval share a start
    idx_keyed = idx.set_index(["code", "aoi", "acq_start", "acq_end"]).sort_index()

    labels_rows, mask_rows = [], []
    parts = sorted(src.glob("labels_*.parquet"))
    for i, p in enumerate(parts):
        g = gpd.read_parquet(p)
        g.geometry = g.geometry.simplify(SIMPLIFY_FLOOD).make_valid()
        for r in g.itertuples():
            key = (r.code, r.aoi, r.acq_start, r.acq_end)
            m = idx_keyed.loc[key] if key in idx_keyed.index else None
            if m is not None and isinstance(m, pd.DataFrame):
                raise ValueError(f"label_index not unique on interval key {key}")
            labels_rows.append(
                {
                    "code": r.code,
                    "aoi": r.aoi,
                    "label_day": r.label_day,
                    "acq_start": str(r.acq_start),
                    "sensor": None if m is None else m.sensor,
                    "acq_method": None if m is None else m.acq_method,
                    "acq_precision": None if m is None else m.acq_precision,
                    "area_km2": None if m is None else m.area_km2,
                    "geometry": r.geometry,
                }
            )
            if r.valid_geometry is not None:
                mask_rows.append(
                    {
                        "code": r.code,
                        "aoi": r.aoi,
                        "acq_start": str(r.acq_start),
                        "geometry": r.valid_geometry.simplify(SIMPLIFY_MASK),
                    }
                )
        if (i + 1) % 50 == 0:
            print(f"  merged {i + 1}/{len(parts)} partitions", flush=True)

    (cat / "labels").mkdir(parents=True, exist_ok=True)
    (cat / "valid-masks").mkdir(parents=True, exist_ok=True)
    (cat / "label-index").mkdir(parents=True, exist_ok=True)
    labels = gpd.GeoDataFrame(labels_rows, geometry="geometry", crs="EPSG:4326")
    labels.to_parquet(cat / "labels" / "labels.parquet", compression="zstd")
    masks = gpd.GeoDataFrame(mask_rows, geometry="geometry", crs="EPSG:4326")
    masks.geometry = masks.geometry.make_valid()
    masks.to_parquet(cat / "valid-masks" / "valid_masks.parquet", compression="zstd")
    # Portolan tracks only geospatial files; the index's bboxes are honest
    # geometry anyway (hyparquet consumers simply skip the geometry column)
    from shapely.geometry import box

    idx_geo = gpd.GeoDataFrame(
        idx,
        geometry=[box(r.minx, r.miny, r.maxx, r.maxy) for r in idx.itertuples()],
        crs="EPSG:4326",
    )
    idx_geo.to_parquet(cat / "label-index" / "label_index.parquet", compression="zstd")
    print(
        f"labels: {len(labels)} rows "
        f"({(cat / 'labels' / 'labels.parquet').stat().st_size / 1e6:.0f} MB simplified); "
        f"masks: {len(masks)}; index: {len(idx)}"
    )


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default="/tmp/gie_cems_flood_platinum/gold_src", type=Path)
    ap.add_argument("--catalog", default="/tmp/gie_cems_flood_platinum/catalog", type=Path)
    ap.add_argument("--stage", default="dev", choices=["dev", "prod"])
    ap.add_argument("--push", action="store_true", help="push to blob after building")
    ap.add_argument("--skip-build", action="store_true", help="push existing catalog only")
    args = ap.parse_args(argv)

    cat = args.catalog
    cat.mkdir(parents=True, exist_ok=True)
    if not (cat / ".portolan" / "config.yaml").exists():
        _portolan(["init", "--auto", "--title", "CEMS Flood Label Corpus"], cwd=cat)

    if not args.skip_build:
        build_collections(args.src, cat)
        _portolan(["add", "--pmtiles", "labels/labels.parquet"], cwd=cat)
        _portolan(["add", "--pmtiles", "valid-masks/valid_masks.parquet"], cwd=cat)
        _portolan(["add", "label-index/label_index.parquet"], cwd=cat)
        _portolan(["check"], cwd=cat)

    if args.push:
        settings = common.global_settings(args.stage)
        env = {
            "AZURE_STORAGE_ACCOUNT_NAME": settings.account_name,
            "AZURE_STORAGE_SAS_KEY": settings.sas_token(write=True).lstrip("?"),
        }
        _portolan(["push", DEST, "--force"], cwd=cat, env=env)
        print(f"platinum <- {DEST}")


if __name__ == "__main__":
    main()
