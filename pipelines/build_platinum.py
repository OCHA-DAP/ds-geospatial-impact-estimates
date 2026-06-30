"""Build the platinum serving tier: PMTiles + STAC catalog from existing geometry.

The v2 client-side viewer reads heavy geometry as PMTiles directly from blob
(viewport-streamed), instead of full GeoJSON from the server. This converts each
configured vector layer to PMTiles with Portolan (tippecanoe) and pushes them to
the `platinum/` catalog — the lean, browser-read serving tier. It is **additive**:
it only ever writes under `platinum/`; bronze/silver/gold are untouched, and the
live app is undisturbed.

The build is uniform across layers; turning a converted layer *on* in the viewer
is a separate, per-layer step — flip its entry in the client LAYER_SERVING
registry (web/src/main.ts) from "deckgl" to "pmtiles" once its MapLibre styling
is in place. (Polygon layers = a fill; points = a circle; admin/H3 choropleths
also need the hyparquet + setFeatureState value join — Phase 2.)

Run: GIE_BLOB_ACCOUNT_PREFIX=... uv run --group etl python pipelines/build_platinum.py
Deps: portolan-cli[pmtiles]  +  tippecanoe  (brew install tippecanoe).
"""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
from pathlib import Path

import geopandas as gpd
import ocha_stratus as stratus
import pandas as pd

from gie import ledger
from gie.config import load_settings

ADM0 = "VE"
STAGE = "dev"

# collection (= platinum/ subdir) -> (layer, blob path, optional (lon, lat) cols).
# If (lon, lat) is given, the parquet is non-geo (e.g. building_flags) and point
# geometry is built before tiling. Rebuilt+pushed every run = authoritative.
LAYERS: dict[str, tuple[str, str, tuple[str, str] | None]] = {
    "native-microsoft": ("silver", f"source=microsoft/adm0={ADM0}/footprints.parquet", None),
    "native-cems": ("silver", f"source=copernicus_ems/adm0={ADM0}/builtup_damage.parquet", None),
    "native-hot_osm": ("silver", f"source=hot_osm/adm0={ADM0}/damage_points.parquet", None),
    "admin-adm1": ("bronze", f"source=codab/adm0={ADM0}/adm1.parquet", None),
    "admin-adm2": ("bronze", f"source=codab/adm0={ADM0}/adm2.parquet", None),
    "admin-adm3": ("bronze", f"source=codab/adm0={ADM0}/adm3.parquet", None),
    # assessed buildings (per-source damage/analysed flags) — the heavy Overture +
    # agreement views; lon/lat -> points so one tile serves every source.
    "buildings": ("gold", f"model=common/adm0={ADM0}/building_flags.parquet", ("lon", "lat")),
}


def _portolan(args: list[str], cwd: str, env: dict | None = None) -> None:
    """Run a portolan command; init prompts are answered with empty input."""
    r = subprocess.run(
        ["portolan", *args],
        cwd=cwd,
        env={**os.environ, **(env or {})},
        input=b"\n\n",
        capture_output=True,
    )
    if r.returncode != 0:
        print(r.stdout.decode(errors="replace")[-1500:])
        print(r.stderr.decode(errors="replace")[-1500:])
        raise RuntimeError(f"portolan {' '.join(args)} failed ({r.returncode})")


def main() -> None:
    settings = load_settings(STAGE)
    dest = f"az://{settings.container}/{settings.project_prefix}/platinum"

    with tempfile.TemporaryDirectory() as cat:
        _portolan(["init"], cwd=cat)
        for coll, (layer, rel, xy) in LAYERS.items():
            raw = stratus.load_blob_data(
                settings.blob_path(layer, rel), stage=STAGE, container_name=settings.container
            )
            d = Path(cat) / coll
            d.mkdir(parents=True, exist_ok=True)
            out = d / Path(rel).name
            if xy:  # non-geo parquet (lon/lat) -> GeoParquet points before tiling
                df = pd.read_parquet(io.BytesIO(raw))
                gpd.GeoDataFrame(
                    df, geometry=gpd.points_from_xy(df[xy[0]], df[xy[1]]), crs="EPSG:4326"
                ).to_parquet(out)
            else:
                out.write_bytes(raw)
            _portolan(["add", "--pmtiles", str(out)], cwd=cat)
            print(f"  built {coll}  ({len(raw) / 1e6:.1f} MB source)", flush=True)

        env = {
            "AZURE_STORAGE_ACCOUNT_NAME": settings.account_name,
            "AZURE_STORAGE_SAS_KEY": settings.sas_token(write=True).lstrip("?"),
        }
        # --force: platinum is fully derived from this config, so rebuild authoritatively.
        _portolan(["push", dest, "--force"], cwd=cat, env=env)

    ledger.record(
        "platinum",
        "platinum",
        "PMTiles serving tier (v2 client-side) — heavy geometry as tiles",
        dest,
        f"collections: {', '.join(LAYERS)}",
    )
    print(f"platinum <- {dest}  ({len(LAYERS)} collections)")


if __name__ == "__main__":
    main()
