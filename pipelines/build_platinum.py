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

Incremental: a persistent catalog (GIE_PLATINUM_CATALOG, default /tmp/gie_platinum_catalog)
lets Portolan skip re-tiling unchanged collections and push only what changed. Pass
collection names to process just those — e.g. after a new Microsoft AOI:
    uv run ... build_platinum.py native-microsoft buildings
With no args, all collections are processed (unchanged ones are no-ops after run 1).

Run: GIE_BLOB_ACCOUNT_PREFIX=... uv run --group etl python pipelines/build_platinum.py [collection ...]
Deps: portolan-cli[pmtiles]  +  tippecanoe  (brew install tippecanoe).
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import geopandas as gpd
import ocha_stratus as stratus
import pandas as pd

from gie import blobio, db, ledger
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
    "native-disha": ("silver", f"source=disha/adm0={ADM0}/damage_points.parquet", None),
    "native-unep_debris": ("silver", f"source=unep_debris/adm0={ADM0}/debris.parquet", None),
    "native-uh": ("silver", f"source=uh/adm0={ADM0}/footprints.parquet", None),
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


# Explicit tippecanoe flags for the buildings point layer (515k points, wide area).
# Portolan's default (auto ~z12 + drop-densest) drops the densest coastal tiles'
# features, wiping out sparse per-source damaged sets like DISHA's 193 so their flag
# never lands in a tile. -z14 + no feature/size limit keeps every building at maxzoom
# (default drop-rate still thins low zooms), for ~15% more bytes. See the DISHA note.
BUILDINGS_TIPPE = ["-z14", "--no-tile-size-limit", "--no-feature-limit"]


def _tile_buildings(gdf, settings) -> None:
    """Tile the buildings point layer with explicit tippecanoe flags + upload direct,
    bypassing Portolan (which doesn't cleanly expose maxzoom / drop control)."""
    with tempfile.TemporaryDirectory() as td:
        fgb, pmt = f"{td}/buildings.fgb", f"{td}/building_flags.pmtiles"
        gdf.to_file(fgb, driver="FlatGeobuf")
        r = subprocess.run(
            ["tippecanoe", "-o", pmt, *BUILDINGS_TIPPE, "-l", "building_flags", "--force", fgb],
            capture_output=True,
        )
        if r.returncode != 0:
            print(r.stderr.decode(errors="replace")[-1200:])
            raise RuntimeError(f"tippecanoe buildings tile failed ({r.returncode})")
        data = Path(pmt).read_bytes()
    dest = settings.blob_path("platinum", "buildings", "building_flags.pmtiles")
    blobio.upload(blobio.uploader(settings), data, dest)
    print(f"  buildings <- {dest}  (z14 no-drop, {len(data) / 1e6:.0f} MB)", flush=True)


def export_values(settings) -> None:
    """Write the slim admin facts parquet for client-side hyparquet reads.

    facts.parquet is dominated by ~926k h3 rows; the admin choropleth needs only
    the ~12k adm1/2/3 rows. Writing just those to platinum/values keeps the
    browser read tiny. Snappy (not zstd) so plain hyparquet can decode it. (H3
    values get their own slim file when H3 is converted.)
    """
    con = db.connect()
    src = settings.az_path("gold", "model=common", f"adm0={ADM0}", "facts.parquet")
    df = con.execute(
        f"SELECT source, unit_type, unit_id, unit_name, metric, value "
        f"FROM read_parquet('{src}') WHERE unit_type IN ('adm1', 'adm2', 'adm3')"
    ).df()
    dest = f"{settings.project_prefix}/platinum/values/facts-admin.parquet"
    stratus.upload_parquet_to_blob(
        df, dest, stage=STAGE, container_name=settings.container, compression="snappy"
    )
    print(f"  values <- {dest}  ({len(df):,} admin rows)", flush=True)


def main(only: list[str] | None = None) -> None:
    settings = load_settings(STAGE)
    dest = f"az://{settings.container}/{settings.project_prefix}/platinum"
    # Persistent catalog: Portolan only re-tiles changed sources and pushes changed
    # collections. The dir retains every collection across runs, so a partial run
    # (only=...) re-tiles just those while push still includes the rest. Run a full
    # build (no args) once to populate it.
    cat = Path(os.getenv("GIE_PLATINUM_CATALOG", "/tmp/gie_platinum_catalog"))
    cat.mkdir(parents=True, exist_ok=True)
    if not (cat / ".portolan" / "config.yaml").exists():
        _portolan(["init"], cwd=str(cat))

    sel = {k: v for k, v in LAYERS.items() if not only or k in only}
    if not sel:
        raise SystemExit(f"No collection matches {only}; choose from {list(LAYERS)}")
    for coll, (layer, rel, xy) in sel.items():
        raw = stratus.load_blob_data(
            settings.blob_path(layer, rel), stage=STAGE, container_name=settings.container
        )
        d = cat / coll
        d.mkdir(parents=True, exist_ok=True)
        out = d / Path(rel).name
        if xy:  # non-geo parquet (lon/lat) -> GeoParquet points before tiling
            df = pd.read_parquet(io.BytesIO(raw))
            gdf = gpd.GeoDataFrame(
                df, geometry=gpd.points_from_xy(df[xy[0]], df[xy[1]]), crs="EPSG:4326"
            )
            if coll == "buildings":  # explicit tiling (no drop) + direct upload
                _tile_buildings(gdf, settings)
                shutil.rmtree(d, ignore_errors=True)  # keep it out of the Portolan push
                continue
            gdf.to_parquet(out)
        else:
            out.write_bytes(raw)
        _portolan(["add", "--pmtiles", str(out)], cwd=str(cat))
        print(f"  added {coll}  ({len(raw) / 1e6:.1f} MB source)", flush=True)

    env = {
        "AZURE_STORAGE_ACCOUNT_NAME": settings.account_name,
        "AZURE_STORAGE_SAS_KEY": settings.sas_token(write=True).lstrip("?"),
    }
    # Push the whole persistent catalog; Portolan syncs only changed collections.
    _portolan(["push", dest, "--force"], cwd=str(cat), env=env)
    export_values(settings)  # slim values parquet for hyparquet (admin choropleth)
    ledger.record(
        "platinum",
        "platinum",
        "PMTiles serving tier (v2 client-side) — heavy geometry as tiles",
        dest,
        f"collections: {', '.join(LAYERS)}",
    )
    print(f"platinum <- {dest}  (re-tiled {len(sel)} of {len(LAYERS)} collections)")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
