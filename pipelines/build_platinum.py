"""Build the platinum serving tier: PMTiles + STAC catalog from existing geometry.

Registry-driven, one event per run: ``--event <event_id>`` (ADR-0027). The v2
client-side viewer reads heavy geometry as PMTiles directly from blob
(viewport-streamed), instead of full GeoJSON from the server. This converts each
available vector layer to PMTiles with Portolan (tippecanoe) and pushes them to
the event's `platinum/` catalog — the lean, browser-read serving tier. It is
**additive**: it only ever writes under `platinum/`; bronze/silver/gold are
untouched, and the live app is undisturbed.

Which native collections exist is probed per event (a source not harmonized for
this event is skipped and printed — absence is a real per-event state); admin
collections go to the deepest CODAB level the event's country has (VE: adm3,
CO: adm2), and the meta artifacts record the available levels for the SPA
(`sources.json.admin_levels`, `export_meta.json.levels`).

Incremental: a persistent PER-EVENT catalog (GIE_PLATINUM_CATALOG override;
default /tmp/gie_platinum_catalog for the VE event — its pre-existing cache —
and /tmp/gie_platinum_catalog-<event> otherwise) lets Portolan skip re-tiling
unchanged collections and push only what changed. The catalog is stamped with
its event and refuses to serve another (a shared catalog would cross-push
events). Pass collection names to process just those.

Run: uv run --group etl python pipelines/build_platinum.py --event <event_id> [collection ...]
Deps: portolan-cli[pmtiles]  +  tippecanoe  (brew install tippecanoe).
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import geopandas as gpd
import ocha_stratus as stratus
import pandas as pd

from gie import blobio, codab, db, events, ledger
from gie.config import (
    OSU_PUBLISHED_VERSION,
    common_segments,
    load_settings,
    source_segments,
)

STAGE = "dev"
LEGACY_CATALOG_EVENT = "20260624-ve-earthquake"  # keeps its pre-existing cache dir

# collection -> silver filename parts appended to source_segments(src, event).
NATIVE_CANDIDATES: dict[str, tuple[str, list[str]]] = {
    "native-microsoft": ("microsoft", ["footprints.parquet"]),
    "native-impact_initiatives": ("impact_initiatives", ["building_damage.parquet"]),
    "native-osu": ("osu", [f"version={OSU_PUBLISHED_VERSION}", "damage_footprints.parquet"]),
    "native-cems": ("copernicus_ems", ["builtup_damage.parquet"]),
    "native-hot_osm": ("hot_osm", ["damage_points.parquet"]),
    "native-disha": ("disha", ["damage_points.parquet"]),
    "native-unep_debris": ("unep_debris", ["debris.parquet"]),
    "native-uh": ("uh", ["footprints.parquet"]),
}


def _layers(settings, cc, eid: str, adm0: str, deepest: int) -> dict:
    """collection -> (layer, [path parts], coll_event, (lon,lat)|None), probed
    against blob so only collections that exist for this event are built."""
    layers: dict[str, tuple[str, list[str], str | None, tuple[str, str] | None]] = {}
    for coll, (src, tail) in NATIVE_CANDIDATES.items():
        parts = [*source_segments(src, eid), *tail]
        if cc.get_blob_client(settings.blob_path("silver", *parts, event=eid)).exists():
            layers[coll] = ("silver", parts, eid, None)
        else:
            print(f"  skip {coll}: not harmonized for {eid}", flush=True)
    for lvl in range(1, deepest + 1):
        # admin-* collections are CODAB (shared reference data, spec §3): event=None.
        layers[f"admin-adm{lvl}"] = (
            "bronze", ["source=codab", f"adm0={adm0}", f"adm{lvl}.parquet"], None, None
        )
    # assessed buildings (per-source damage/analysed flags) — the heavy Overture +
    # agreement views; lon/lat -> points so one tile serves every source.
    layers["buildings"] = (
        "gold", [*common_segments(eid, adm0), "building_flags.parquet"], eid, ("lon", "lat")
    )
    return layers


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


def _tile_buildings(gdf, settings, eid: str) -> None:
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
    dest = settings.blob_path("platinum", "buildings", "building_flags.pmtiles", event=eid)
    blobio.upload(blobio.uploader(settings), data, dest)
    print(f"  buildings <- {dest}  (z14 no-drop, {len(data) / 1e6:.0f} MB)", flush=True)


def export_values(settings, eid: str, adm0: str, deepest: int) -> None:
    """Write the slim admin facts parquet for client-side hyparquet reads.

    facts.parquet is dominated by the h3 rows; the admin choropleth needs only
    the admin rows. Snappy (not zstd) so plain hyparquet can decode it."""
    con = db.connect()
    src = settings.az_path("gold", *common_segments(eid, adm0), "facts.parquet", event=eid)
    lvls = ", ".join(f"'adm{i}'" for i in range(1, deepest + 1))
    df = con.execute(
        f"SELECT source, unit_type, unit_id, unit_name, metric, value "
        f"FROM read_parquet('{src}') WHERE unit_type IN ({lvls})"
    ).df()
    dest = settings.blob_path("platinum", "values", "facts-admin.parquet", event=eid)
    stratus.upload_parquet_to_blob(
        df, dest, stage=STAGE, container_name=settings.container, compression="snappy"
    )
    print(f"  values <- {dest}  ({len(df):,} admin rows)", flush=True)


def export_meta(settings, eid: str, adm0: str, deepest: int) -> None:
    """Write the static meta artifacts the viewer reads per event.

    sources.json (now incl. admin_levels — CO has no adm3), extents.json,
    coverage_detail.json, agreement_counts.json, and the Excel-export inputs
    (export-admN parquets for the levels that exist + export_meta.json with
    the level list)."""
    import json

    from gie.serving import (
        METRICS,
        list_sources,
        load_agreement,
        load_coverage_detail,
        load_source_extent,
        methods_for,
    )

    levels = list(range(1, deepest + 1))
    sources = list_sources(adm0, event=eid)
    meta_dir = settings.blob_path("platinum", "meta", event=eid)
    up = lambda name, obj: stratus.upload_blob_data(  # noqa: E731
        json.dumps(obj).encode(), f"{meta_dir}/{name}", stage=STAGE,
        container_name=settings.container, content_type="application/json",
    )
    up("sources.json", {
        "sources": sources, "adm0": adm0, "metrics": METRICS, "admin_levels": levels,
    })
    # Methodology cards for exactly the sources this event has (per-event wording
    # via gie.serving._METHODS_OVERRIDES); the SPA renders these instead of its
    # built-in list when present.
    up("methods.json", {"methods": methods_for(sources, eid)})
    up("extents.json", {
        s: json.loads(load_source_extent(s, adm0, event=eid).to_json()) for s in sources
    })
    up("coverage_detail.json", json.loads(load_coverage_detail(adm0, event=eid).to_json()))
    # Category counts for the agreement-view legend: the geometry comes from the
    # buildings PMTiles (flags are tile properties), but a client can't count
    # unrendered tiles — so the totals are precomputed here.
    counts = load_agreement(adm0, event=eid)["agreement"].value_counts().to_dict()
    up("agreement_counts.json", {k: int(v) for k, v in counts.items()})
    # Excel-export inputs (client-side exceljs, ADR-0011): per-level tidy tables
    # (needs the codab name-hierarchy join, so computed here, not in the browser)
    # + the README text blocks — numbers and wording identical to /api/export.xlsx.
    from gie.serving import _EXPORT_GLOSSARY, _SOURCE_DESC, _SOURCE_SHORT, load_export

    for level in levels:
        stratus.upload_parquet_to_blob(
            load_export(level, adm0, event=eid),
            settings.blob_path("platinum", "values", f"export-adm{level}.parquet", event=eid),
            stage=STAGE, container_name=settings.container, compression="snappy",
        )
    src_desc = "Damage source (one row per source per unit): " + "; ".join(
        _SOURCE_DESC[s] for s in sources if s in _SOURCE_DESC
    ) + "."
    up("export_meta.json", {
        "subtitle_sources": [_SOURCE_SHORT.get(s, s) for s in sources],
        "glossary": _EXPORT_GLOSSARY[:2] + [["source", src_desc]] + _EXPORT_GLOSSARY[2:],
        "levels": levels,
    })
    print(f"  meta <- {meta_dir}/ (sources, extents x{len(sources)}, coverage_detail, "
          f"agreement_counts, export x{len(levels)}+meta)", flush=True)


def export_h3(settings, eid: str, adm0: str) -> None:
    """H3-view assets: hex-cell polygon tiles + per-source slim values parquet."""
    from gie.serving import list_sources, load_common_h3

    con = db.connect()
    src = settings.az_path("gold", *common_segments(eid, adm0), "facts.parquet", event=eid)
    n_sources = 0
    for s in list_sources(adm0, event=eid):
        g = load_common_h3(s, adm0, event=eid)
        dest = settings.blob_path("platinum", "values", f"facts-h3-{s}.parquet", event=eid)
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
    dest = settings.blob_path("platinum", "h3", "h3_cells.pmtiles", event=eid)
    blobio.upload(blobio.uploader(settings), data, dest)
    print(f"  h3 <- {dest}  ({len(gdf):,} cells, {len(data) / 1e6:.1f} MB; "
          f"values x{n_sources} sources)", flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--event", required=True, help="event_id from events.yaml whose platinum to build"
    )
    parser.add_argument(
        "collections", nargs="*",
        help="only these collections (or 'meta' / 'h3'); default: all available",
    )
    args = parser.parse_args(argv)
    only = args.collections or None
    ev = events.get_event(args.event)  # fails loudly on an unregistered event
    if len(ev.countries) != 1:
        raise NotImplementedError(
            f"event {ev.event_id} spans countries {ev.countries} — pick the admin/base "
            "layout for multi-country deliberately."
        )
    eid, adm0 = ev.event_id, ev.countries[0]
    settings = load_settings(STAGE)
    deepest = codab.deepest_level(settings, adm0, stage=STAGE)
    cc = stratus.get_container_client(stage=STAGE, container_name=settings.container)
    dest = settings.az_path("platinum", event=eid)

    # Persistent PER-EVENT catalog: Portolan only re-tiles changed sources and pushes
    # changed collections. The dir retains every collection across runs, so a partial
    # run (only=...) re-tiles just those while push still includes the rest. Stamped
    # with its event — a shared/reused dir would silently cross-push events.
    default_cat = (
        "/tmp/gie_platinum_catalog"  # the VE catalog predates per-event dirs — keep its cache
        if eid == LEGACY_CATALOG_EVENT
        else f"/tmp/gie_platinum_catalog-{eid}"
    )
    cat = Path(os.getenv("GIE_PLATINUM_CATALOG", default_cat))
    cat.mkdir(parents=True, exist_ok=True)
    stamp = cat / ".gie-event"
    if stamp.exists() and stamp.read_text().strip() != eid:
        raise RuntimeError(
            f"catalog {cat} belongs to event {stamp.read_text().strip()!r}, not {eid!r} — "
            "use a distinct GIE_PLATINUM_CATALOG per event."
        )
    stamp.write_text(eid)
    if not (cat / ".portolan" / "config.yaml").exists():
        _portolan(["init"], cwd=str(cat))

    if only == ["meta"]:  # just the static meta artifacts — no tiling/push needed
        export_meta(settings, eid, adm0, deepest)
        return
    if only == ["h3"]:  # just the H3 tiles + values
        export_h3(settings, eid, adm0)
        return
    layers = _layers(settings, cc, eid, adm0, deepest)
    sel = {k: v for k, v in layers.items() if not only or k in only}
    if not sel:
        raise SystemExit(f"No collection matches {only}; choose from {list(layers)} or 'meta'")
    for coll, (layer, parts, coll_event, xy) in sel.items():
        raw = stratus.load_blob_data(
            settings.blob_path(layer, *parts, event=coll_event),
            stage=STAGE, container_name=settings.container,
        )
        d = cat / coll
        d.mkdir(parents=True, exist_ok=True)
        out = d / parts[-1]
        if xy:  # non-geo parquet (lon/lat) -> GeoParquet points before tiling
            df = pd.read_parquet(io.BytesIO(raw))
            gdf = gpd.GeoDataFrame(
                df, geometry=gpd.points_from_xy(df[xy[0]], df[xy[1]]), crs="EPSG:4326"
            )
            if coll == "buildings":  # explicit tiling (no drop) + direct upload
                _tile_buildings(gdf, settings, eid)
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
    export_values(settings, eid, adm0, deepest)  # slim admin values for hyparquet
    export_meta(settings, eid, adm0, deepest)  # static sources/extents/coverage JSON
    export_h3(settings, eid, adm0)  # H3 hex tiles + per-source values
    ledger.record(
        "platinum",
        "platinum",
        f"PMTiles serving tier (v2 client-side) — {ev.name}",
        dest,
        f"collections: {', '.join(layers)}",
    )
    print(f"platinum <- {dest}  (re-tiled {len(sel)} of {len(layers)} collections)")


if __name__ == "__main__":
    main()
