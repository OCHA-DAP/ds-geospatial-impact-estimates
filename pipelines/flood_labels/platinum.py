"""Platinum: the published display catalog over BOTH flood-label corpora —
CEMS gold v1 and UNOSAT gold v2 — a versioned Portolan catalog (STAC +
GeoParquet + PMTiles) read by pages/flood-labels/ through the token issuer.

Collections (see gie.flood_labels.platinum for the rules):
  water        UNOSAT water at acquisition (geom_water), display-simplified. PMTiles.
  flood        UNOSAT geom_flood where the source separated it + every CEMS
               flood extent. PMTiles.
  valid-masks  analysed-area masks of both, heavily simplified. PMTiles.
  label-index  the union of both indexes, thin display columns, bbox geometry
               (the page reads it client-side with hyparquet).

Reads gold from blob per code, one geometry column at a time, smallest code
first. A local UNOSAT work dir (`--unosat-work-dir`, the gold mirror the gold
run left behind) is used for any file whose size matches the blob listing;
everything else is downloaded once into `{work_dir}/gold_cache/`.

Nothing is skipped silently: a code named in `--skip-codes` is recorded in
build_summary.json under `skipped_by_flag`; any other failure stops the run.
Unlike the event viewer's platinum, versions.json here IS a record — update
via `portolan sync`; never hand-delete the remote directory.

Prereqs: portolan-cli, tippecanoe, GDAL (ogr2ogr), ocha-stratus SAS in .env.
Run:  uv run --group etl --group api python pipelines/flood_labels/platinum.py \
          [--unosat-work-dir DIR] [--codes ...] [--limit N] [--push]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

from gie.flood_labels import platinum as P

DEST = "az://global/flood_labels/platinum"
CATALOG_TITLE = "Flood Label Corpus (CEMS + UNOSAT)"
COLLECTION_DIRS = {"water": "water", "flood": "flood", "masks": "valid-masks"}
COLLECTION_FILES = {
    "water": "water.parquet",
    "flood": "flood.parquet",
    "masks": "valid_masks.parquet",
}
# Tile zoom ceiling per collection. z10 is ~150 m/px at the equator; the map
# overzooms past it, so an event view shows z10 geometry (a 33 m UNOSAT
# staircase is sub-pixel there anyway). Measured: water 546 s, flood ~10 min,
# each 5M exploded features, at z10 on 8 cores. Masks are context, drawn as
# dashed outlines: z9 (1,122 s for 510k features) is plenty.
MAX_ZOOM = {"water": 10, "flood": 10, "masks": 9}


def _pmtiles(parquet: Path, layer: str, max_zoom: int, log: Path) -> Path:
    """GeoParquet -> PMTiles, our way: GDAL writes 2-D line-delimited GeoJSON
    to a temp file, ONE FEATURE PER POLYGON PART (`-explodecollections`: a
    508k-part footprint as one feature is clipped into every tile it touches
    at every zoom; as 508k small features it is tippecanoe's normal case —
    measured 3,109 s vs 1,122 s on the masks at z9), and tippecanoe reads it
    in parallel (`-P` needs a file, not a pipe) with a zoom ceiling. Not
    portolan's built-in path, which streams through DuckDB spatial and
    rejects the self-intersecting polygons that non-topology-preserving
    simplification (and CEMS's own rings) contain
    (`TopologyException: side location conflict`); tippecanoe itself cleans
    rings as it tiles. Fewer switches than portolan uses: its
    `--no-simplification-of-shared-nodes` costs a global shared-vertex pass
    (single-threaded, 98% CPU for over ten minutes on the 51 MB masks file),
    and label polygons share no borders worth preserving; its
    `--no-tile-size-limit` is not wanted for a display product either.
    `portolan add --pmtiles` then tracks the file it finds instead of
    regenerating it (it only rebuilds when the source is newer)."""
    out = parquet.with_suffix(".pmtiles")
    seq = parquet.with_suffix(".geojsonl")
    if out.exists() and out.stat().st_mtime > parquet.stat().st_mtime:
        # portolan's own rule: a PMTiles newer than its source is current
        print(f"pmtiles {out.name}: reusing ({out.stat().st_size / 1e6:.0f} MB, newer than source)")
        return out
    t = time.time()
    with open(log, "a") as f:
        f.write(f"\n=== ogr2ogr -> {seq.name}\n")
        f.flush()
        r = subprocess.run(
            [
                "ogr2ogr",
                "-f",
                "GeoJSONSeq",
                "-dim",
                "XY",
                "-explodecollections",
                str(seq),
                str(parquet),
            ],
            stdout=f,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"ogr2ogr failed ({r.returncode}) on {parquet}; see {log}")
        f.write(f"=== tippecanoe -> {out.name} (z{max_zoom})\n")
        f.flush()
        r = subprocess.run(
            [
                "tippecanoe",
                "-P",
                "-o",
                str(out),
                "-l",
                layer,
                "-z",
                str(max_zoom),
                "--drop-densest-as-needed",
                "--force",
                str(seq),
            ],
            stdout=f,
            stderr=subprocess.STDOUT,
            text=True,
        )
    seq.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError(f"tippecanoe failed ({r.returncode}) on {parquet}; see {log}")
    mb = out.stat().st_size / 1e6
    print(f"pmtiles {out.name}: {mb:.0f} MB, z{max_zoom}, {time.time() - t:.0f}s", flush=True)
    return out


def _portolan(args: list[str], cwd: Path, env: dict | None = None) -> None:
    """Run portolan in the catalog. tippecanoe's progress output (tens of KB
    per collection) goes to `{catalog}/portolan.log`, the outcome to stdout;
    a non-zero exit raises with the log's tail."""
    log = cwd / "portolan.log"
    with open(log, "a") as f:
        f.write(f"\n=== portolan {' '.join(args)}\n")
        f.flush()
        r = subprocess.run(
            ["portolan", *args],
            cwd=str(cwd),
            input="",
            text=True,
            stdout=f,
            stderr=subprocess.STDOUT,
            env={**os.environ, **(env or {})},
        )
    tail = log.read_text().splitlines()[-6:]
    print(f"portolan {' '.join(args)}: exit {r.returncode}", flush=True)
    for line in tail:
        if line.startswith(("✓", "⚠", "✗", "→")) or "Error" in line:
            print("   ", line[-160:], flush=True)
    if r.returncode != 0:
        raise RuntimeError(f"portolan {' '.join(args)} failed ({r.returncode}); see {log}")


def _read_blob_parquet(cc, path: str) -> pd.DataFrame:
    import io

    return pd.read_parquet(io.BytesIO(cc.download_blob(path).readall()))


def _list_codes(cc, source: str) -> dict[str, int]:
    """code -> labels file size, from the blob listing (the listing decides)."""
    prefix = P.labels_prefix(source)
    out: dict[str, int] = {}
    for b in cc.list_blobs(name_starts_with=prefix):
        if not b.name.endswith("/data.parquet"):
            continue
        code = b.name[len(prefix) :].split("/")[0]
        out[code] = b.size
    return out


def _local_labels(
    cc, source: str, code: str, size: int, cache: Path, unosat_work_dir: Path | None
) -> Path:
    """A local copy of one labels file whose size matches the listing: the
    UNOSAT gold mirror if it has it, else the download cache, else download."""
    blob_path = P.labels_path(source, code)
    candidates = []
    if source == "unosat" and unosat_work_dir is not None:
        candidates.append(unosat_work_dir / blob_path.removeprefix("unosat/"))
    cached = cache / blob_path
    candidates.append(cached)
    for c in candidates:
        if c.exists() and c.stat().st_size == size:
            return c
    cached.parent.mkdir(parents=True, exist_ok=True)
    tmp = cached.with_suffix(".part")
    with open(tmp, "wb") as f:
        cc.download_blob(blob_path).readinto(f)
    got = tmp.stat().st_size
    if got != size:
        tmp.unlink()
        raise OSError(f"{blob_path}: downloaded {got} bytes, listing says {size}")
    tmp.replace(cached)
    return cached


def _build_one(job: tuple) -> tuple[dict, dict, float]:
    """Worker: one code's display rows. Builds its own blob client (clients do
    not cross process boundaries) and reads the display index from disk."""
    source, code, size, cache, unosat_work_dir, stage, index_file = job
    import ocha_stratus as stratus

    t = time.time()
    cc = stratus.get_container_client(container_name="global", stage=stage)
    index = pd.read_parquet(index_file)
    path = _local_labels(
        cc, source, code, size, Path(cache), Path(unosat_work_dir) if unosat_work_dir else None
    )
    got, counts = P.display_rows(source, path, index)
    return got, counts, time.time() - t


def build(args, cc) -> dict:
    cat: Path = args.work_dir / "catalog"
    cache: Path = args.work_dir / "gold_cache"
    cat.mkdir(parents=True, exist_ok=True)

    # 1. the index, harmonised and combined
    hdx = _read_blob_parquet(cc, P.HDX_DATASETS) if "unosat" in args.sources else None
    frames = [
        P.harmonise_index(s, _read_blob_parquet(cc, P.index_path(s)), hdx) for s in args.sources
    ]
    index = P.combine_index(frames)
    print(
        "index: "
        + ", ".join(f"{s}={int((index.label_source == s).sum())}" for s in args.sources)
        + f" label sets, {index.code.nunique()} codes",
        flush=True,
    )

    # 2. which codes, in what order (cheapest first, so progress is visible early)
    listed = {s: _list_codes(cc, s) for s in args.sources}
    for s in args.sources:
        in_index = set(index.loc[index.label_source == s, "code"])
        no_file = sorted(in_index - set(listed[s]))
        if no_file:
            raise FileNotFoundError(
                f"{s}: {len(no_file)} index codes have no labels file: {no_file[:5]}"
            )
    todo = sorted(
        ((s, c, n) for s in args.sources for c, n in listed[s].items()),
        key=lambda t: t[2],
    )
    if args.codes:
        wanted = {c.strip() for c in args.codes.split(",") if c.strip()}
        todo = [t for t in todo if t[1] in wanted]
        missing = wanted - {t[1] for t in todo}
        if missing:
            raise KeyError(f"--codes not found in any listed gold: {sorted(missing)}")
    skip = {c.strip() for c in (args.skip_codes or "").split(",") if c.strip()}
    skipped = [t for t in todo if t[1] in skip]
    todo = [t for t in todo if t[1] not in skip]
    if args.limit is not None:
        todo = todo[: args.limit]
    print(f"codes to build: {len(todo)} (skipped by flag: {len(skipped)})", flush=True)

    # 3. display rows, per code, in worker processes (each code is independent;
    #    the parent only concatenates). Smallest first, so progress shows early.
    rows: dict[str, list[dict]] = {"water": [], "flood": [], "masks": []}
    absent: dict[str, int] = {}
    per_code: list[dict] = []
    t_all = time.time()
    index_file = args.work_dir / "display_index.parquet"
    index.to_parquet(index_file)
    jobs = [
        (
            source,
            code,
            size,
            str(cache),
            str(args.unosat_work_dir or ""),
            args.stage,
            str(index_file),
        )
        for source, code, size in todo
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i, ((source, code, size), (got, counts, secs)) in enumerate(
            zip(todo, pool.map(_build_one, jobs, chunksize=1), strict=True), 1
        ):
            for k, v in got.items():
                rows[k].extend(v)
            for k, v in counts.items():
                absent[k] = absent.get(k, 0) + v
            n = {k: len(v) for k, v in got.items()}
            per_code.append(
                {
                    "source": source,
                    "code": code,
                    "bytes": size,
                    "rows": n,
                    "seconds": round(secs, 1),
                }
            )
            print(
                f"[{i}/{len(todo)}] {source} {code} {size / 1e6:8.1f} MB  "
                f"water={n['water']} flood={n['flood']} masks={n['masks']}  {secs:6.1f}s",
                flush=True,
            )

    # 4. write the collections
    written = {}
    for coll, sub in COLLECTION_DIRS.items():
        d = cat / sub
        d.mkdir(parents=True, exist_ok=True)
        out = d / COLLECTION_FILES[coll]
        if rows[coll]:
            g = gpd.GeoDataFrame(rows[coll], geometry="geometry", crs="EPSG:4326")
            g["acq_start"] = g["acq_start"].astype(str)
            g["acq_end"] = g["acq_end"].astype(str)
        else:
            g = gpd.GeoDataFrame({"code": []}, geometry=gpd.GeoSeries([], crs="EPSG:4326"))
        g.to_parquet(out, compression="zstd")
        written[coll] = {"rows": len(g), "mb": round(out.stat().st_size / 1e6, 1)}
    (cat / "label-index").mkdir(parents=True, exist_ok=True)
    built_codes = {c for _, c, _ in todo}
    idx_out = index[index.code.isin(built_codes)] if (args.codes or args.limit or skip) else index
    idx_geom = P.index_geometry(idx_out)
    idx_geo = gpd.GeoDataFrame(
        idx_out.reset_index(drop=True),
        geometry=gpd.GeoSeries(idx_geom, crs="EPSG:4326"),
        crs="EPSG:4326",
    )
    idx_geo.to_parquet(cat / "label-index" / "label_index.parquet", compression="zstd")

    bad_dates = P.implausible_dates(idx_out)
    summary = {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "stage": args.stage,
        "sources": list(args.sources),
        "simplify_deg": {**P.SIMPLIFY, "masks": P.SIMPLIFY_MASK},
        "index_rows": {s: int((idx_out.label_source == s).sum()) for s in args.sources},
        "codes_built": {s: sum(1 for t in todo if t[0] == s) for s in args.sources},
        "collections": written,
        "label_sets_without_geometry": absent,
        "index_rows_without_bbox": sum(g is None for g in idx_geom),
        "index_rows_with_implausible_dates": json.loads(
            bad_dates.to_json(orient="records", date_format="iso")
        ),
        "skipped_by_flag": [{"source": s, "code": c, "bytes": n} for s, c, n in skipped],
        "seconds_total": round(time.time() - t_all, 1),
        "per_code": per_code,
    }
    (cat / "build_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "per_code"}, indent=2), flush=True)
    return summary


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--stage", default="dev", choices=["dev", "prod"])
    ap.add_argument("--work-dir", default=Path("/tmp/gie_flood_labels_platinum"), type=Path)
    ap.add_argument(
        "--unosat-work-dir",
        default=None,
        type=Path,
        help="a UNOSAT gold run's work dir; its gold/ mirror is used where sizes match the listing",
    )
    ap.add_argument(
        "--sources", default="cems,unosat", help="comma-separated subset of cems,unosat"
    )
    ap.add_argument("--codes", default=None, help="comma-separated event codes (either source)")
    ap.add_argument("--limit", type=int, default=None, help="build only the N smallest codes")
    ap.add_argument(
        "--skip-codes",
        default=None,
        help="codes to leave out deliberately; recorded in build_summary.json, never implicit",
    )
    ap.add_argument("--workers", type=int, default=3, help="codes simplified in parallel")
    ap.add_argument("--push", action="store_true", help="push the catalog to blob after building")
    ap.add_argument("--skip-build", action="store_true", help="push the existing catalog only")
    ap.add_argument(
        "--tiles-only",
        action="store_true",
        help="keep the catalog's parquet files; redo only PMTiles, portolan add/check (and --push)",
    )
    args = ap.parse_args(argv)
    args.sources = tuple(s.strip() for s in args.sources.split(",") if s.strip())
    for s in args.sources:
        if s not in P.SOURCES:
            ap.error(f"unknown source {s!r}")

    import ocha_stratus as stratus

    cc = stratus.get_container_client(container_name="global", stage=args.stage)
    cat = args.work_dir / "catalog"
    cat.mkdir(parents=True, exist_ok=True)
    if not (cat / ".portolan" / "config.yaml").exists():
        _portolan(["init", "--auto", "--title", CATALOG_TITLE], cwd=cat)

    if not args.skip_build:
        if not args.tiles_only:
            build(args, cc)
        for coll, sub in COLLECTION_DIRS.items():
            parquet = cat / sub / COLLECTION_FILES[coll]
            if not parquet.exists():
                raise FileNotFoundError(f"{parquet} missing; run without --tiles-only first")
            _pmtiles(parquet, layer=parquet.stem, max_zoom=MAX_ZOOM[coll], log=cat / "portolan.log")
            # --force: a parquet portolan already tracks is otherwise "unchanged"
            # and its PMTiles, built after that, never gets registered (and so
            # never pushed). Regeneration is governed by --force-pmtiles, not this.
            _portolan(["add", "--pmtiles", "--force", f"{sub}/{COLLECTION_FILES[coll]}"], cwd=cat)
        _portolan(["add", "label-index/label_index.parquet"], cwd=cat)
        _portolan(["check"], cwd=cat)

    if args.push:
        from gie.unosat import common

        settings = common.global_settings(args.stage)
        env = {
            "AZURE_STORAGE_ACCOUNT_NAME": settings.account_name,
            "AZURE_STORAGE_SAS_KEY": settings.sas_token(write=True).lstrip("?"),
        }
        _portolan(["push", DEST, "--force"], cwd=cat, env=env)
        print(f"platinum <- {DEST}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
