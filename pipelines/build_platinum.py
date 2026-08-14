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

from gie import blobio, db, events, ledger
from gie.config import OSU_PUBLISHED_VERSION, load_settings

ADM0 = "VE"
STAGE = "dev"
EVENT = "20260624-ve-earthquake"  # validated against events.yaml in main()

# collection (= platinum/ subdir) -> (layer, blob path, optional (lon, lat) cols).
# If (lon, lat) is given, the parquet is non-geo (e.g. building_flags) and point
# geometry is built before tiling. Rebuilt+pushed every run = authoritative.
LAYERS: dict[str, tuple[str, str, tuple[str, str] | None]] = {
    "native-microsoft": ("silver", f"source=microsoft/adm0={ADM0}/footprints.parquet", None),
    "native-impact_initiatives": ("silver", f"source=impact_initiatives/adm0={ADM0}/building_damage.parquet", None),
    "native-osu": ("silver", f"source=osu/adm0={ADM0}/version={OSU_PUBLISHED_VERSION}/damage_footprints.parquet", None),
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
    dest = settings.blob_path("platinum", "buildings", "building_flags.pmtiles", event=EVENT)
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
    src = settings.az_path("gold", "model=common", f"adm0={ADM0}", "facts.parquet", event=EVENT)
    df = con.execute(
        f"SELECT source, unit_type, unit_id, unit_name, metric, value "
        f"FROM read_parquet('{src}') WHERE unit_type IN ('adm1', 'adm2', 'adm3')"
    ).df()
    dest = f"{settings.project_prefix}/platinum/values/facts-admin.parquet"
    stratus.upload_parquet_to_blob(
        df, dest, stage=STAGE, container_name=settings.container, compression="snappy"
    )
    print(f"  values <- {dest}  ({len(df):,} admin rows)", flush=True)


def export_meta(settings) -> None:
    """Write the static meta artifacts the viewer previously fetched from the API.

    sources.json, extents.json (all sources combined -> one request instead of one
    per source), and coverage_detail.json are constant between data refreshes, so
    serving them from the API recomputed them per cold cache for nothing — and they
    were the single-worker contention behind the slow first load (ADR-0021). Written
    tier-aware (platinum/ or platinum-prod/ via GIE_TIER) since each tier's meta
    derives from its own gold.
    """
    import json

    from gie.serving import (
        METRICS,
        list_sources,
        load_agreement,
        load_coverage_detail,
        load_source_extent,
    )

    sources = list_sources(ADM0)
    meta_dir = settings.blob_path("platinum", "meta", event=EVENT)
    up = lambda name, obj: stratus.upload_blob_data(  # noqa: E731
        json.dumps(obj).encode(), f"{meta_dir}/{name}", stage=STAGE,
        container_name=settings.container, content_type="application/json",
    )
    up("sources.json", {"sources": sources, "adm0": ADM0, "metrics": METRICS})
    up("extents.json", {s: json.loads(load_source_extent(s, ADM0).to_json()) for s in sources})
    up("coverage_detail.json", json.loads(load_coverage_detail(ADM0).to_json()))
    # Category counts for the agreement-view legend: the geometry comes from the
    # buildings PMTiles (flags are tile properties), but a client can't count
    # unrendered tiles — so the totals are precomputed here.
    counts = load_agreement(ADM0)["agreement"].value_counts().to_dict()
    up("agreement_counts.json", {k: int(v) for k, v in counts.items()})
    # Excel-export inputs (client-side exceljs, ADR-0011): the three per-level tidy
    # tables (needs the codab name-hierarchy join, so computed here, not in the
    # browser) + the README text blocks composed from the same constants the server
    # export used — numbers and wording stay identical to /api/export.xlsx.
    from gie.serving import _EXPORT_GLOSSARY, _SOURCE_DESC, _SOURCE_SHORT, load_export

    for level in (1, 2, 3):
        stratus.upload_parquet_to_blob(
            load_export(level, ADM0),
            settings.blob_path("platinum", "values", f"export-adm{level}.parquet", event=EVENT),
            stage=STAGE, container_name=settings.container, compression="snappy",
        )
    src_desc = "Damage source (one row per source per unit): " + "; ".join(
        _SOURCE_DESC[s] for s in sources if s in _SOURCE_DESC
    ) + "."
    up("export_meta.json", {
        "subtitle_sources": [_SOURCE_SHORT.get(s, s) for s in sources],
        "glossary": _EXPORT_GLOSSARY[:2] + [["source", src_desc]] + _EXPORT_GLOSSARY[2:],
    })
    print(f"  meta <- {meta_dir}/ (sources, extents x{len(sources)}, coverage_detail, "
          f"agreement_counts, export x3+meta)", flush=True)


def export_h3(settings) -> None:
    """H3-view assets: hex-cell polygon tiles + per-source slim values parquet.

    Cell geometry is pre-generated with DuckDB's h3 extension (ADR-0011) so the
    browser needs no H3 library; the client joins values to tiles by cell id via
    setFeatureState, mirroring the admin choropleth. Values are one slim long-form
    parquet PER SOURCE (the client loads only selected sources). Tier-aware like
    export_meta.
    """
    from gie.serving import list_sources, load_common_h3

    con = db.connect()
    src = settings.az_path("gold", "model=common", f"adm0={ADM0}", "facts.parquet", event=EVENT)
    # WIDE per-source values (one row per cell, metrics as columns) — the long form
    # repeated the h3-id string per metric and weighed ~6.5 MB/source; wide is ~4x
    # smaller and is already the exact row shape the client consumes.
    n_sources = 0
    for s in list_sources(ADM0):
        g = load_common_h3(s, ADM0)
        dest = settings.blob_path("platinum", "values", f"facts-h3-{s}.parquet", event=EVENT)
        stratus.upload_parquet_to_blob(
            g, dest, stage=STAGE, container_name=settings.container, compression="snappy"
        )
        n_sources += 1
    cells = con.execute(
        f"SELECT DISTINCT unit_id AS h3, h3_cell_to_boundary_wkt(unit_id) AS wkt "
        f"FROM read_parquet('{src}') WHERE unit_type='h3'"
    ).df()
    gdf = gpd.GeoDataFrame(
        cells[["h3"]], geometry=gpd.GeoSeries.from_wkt(cells["wkt"]), crs="EPSG:4326"
    )
    with tempfile.TemporaryDirectory() as td:
        fgb, pmt = f"{td}/h3.fgb", f"{td}/h3_cells.pmtiles"
        gdf.to_file(fgb, driver="FlatGeobuf")
        r = subprocess.run(
            ["tippecanoe", "-o", pmt, "-zg", "--no-feature-limit", "--no-tile-size-limit",
             "--detect-shared-borders", "-l", "h3_cells", "--force", fgb],
            capture_output=True,
        )
        if r.returncode != 0:
            print(r.stderr.decode(errors="replace")[-1200:])
            raise RuntimeError(f"tippecanoe h3 tile failed ({r.returncode})")
        data = Path(pmt).read_bytes()
    dest = settings.blob_path("platinum", "h3", "h3_cells.pmtiles", event=EVENT)
    blobio.upload(blobio.uploader(settings), data, dest)
    print(f"  h3 <- {dest}  ({len(gdf):,} cells, {len(data) / 1e6:.1f} MB; "
          f"values x{n_sources} sources)", flush=True)


def main(only: list[str] | None = None) -> None:
    events.require_event(EVENT)
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

    if only == ["meta"]:  # just the static meta artifacts — no tiling/push needed
        export_meta(settings)
        return
    if only == ["h3"]:  # just the H3 tiles + values
        export_h3(settings)
        return
    sel = {k: v for k, v in LAYERS.items() if not only or k in only}
    if not sel:
        raise SystemExit(f"No collection matches {only}; choose from {list(LAYERS)} or 'meta'")
    for coll, (layer, rel, xy) in sel.items():
        # admin-* collections are CODAB (shared reference data, spec §3); everything
        # else is VE-event-scoped.
        coll_event = None if coll.startswith("admin-") else EVENT
        raw = stratus.load_blob_data(
            settings.blob_path(layer, rel, event=coll_event),
            stage=STAGE, container_name=settings.container,
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
    export_meta(settings)  # static sources/extents/coverage JSON (was API-served)
    export_h3(settings)  # H3 hex tiles + per-source values (was API-served)
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
