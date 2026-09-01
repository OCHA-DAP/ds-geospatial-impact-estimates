"""Silver: harmonize the bronze zip corpus into three analysis-ready
GeoParquet tables under global/copernicus_ems/flood/silver/, partitioned by
activation code. Reads zips FROM BRONZE BLOB only (never from CEMS).

  observed_event/code=EMSRnnn/data.parquet
      one row per flood polygon, all five naming eras normalized to one
      schema; raw source attributes preserved verbatim in attrs_json;
      acquisition datetime columns (see below); layer_kind tags the
      supplementary layers (modelled / max_extent / flood_depth).
  coverage/code=EMSRnnn/data.parquet
      AOI, image-footprint and not-analysed polygons: what was actually
      observed, so "no flood polygon" can be read correctly.
  sources/code=EMSRnnn/data.parquet
      one row per (product, image) where the portal API provides it
      (EMSR656+): sensor + acquisition time to the minute.

Acquisition columns on observed_event (the ML-label requirement):
  acq_datetime / acq_window_start / acq_window_end : timestamps (UTC naive)
  acq_precision : minute | date | window
  acq_method    : attribute   (2012-16: per-feature src_date/src_info)
                  api         (2023+: single-image product, exact time)
                  api_window  (2023+: multi-image product, span of its images)
                  window      (2017-23: event_time -> delivery_time; a later
                               catalog-match stage can tighten these)

Processing ledger at silver/_meta/processing.parquet: one row per bronze zip,
status ok | no_extent_layer | error. Absence of flood polygons in a
monitoring product is a real state, recorded, never an error.

Run:  uv run --group etl --group api python pipelines/cems_flood/silver.py
      [--codes EMSR009,EMSR927] [--limit N] [--stage dev]
"""

from __future__ import annotations

import argparse
import io
import json
import re
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import common
import geopandas as gpd
import ocha_lens as lens
import pandas as pd

from gie import blobio

SILVER = "copernicus_ems/flood/silver"
SHP_PARTS = (".shp", ".dbf", ".shx", ".prj")
# dd/mm/yyyy hh:mm inside era-B src_info strings ("COSMO-SkyMed 01/06/2016 17:50")
_SRC_INFO_DT = re.compile(r"(\d{2})/(\d{2})/(\d{4})[ T]+(\d{1,2}):(\d{2})")

EXTENT_COLS = [
    "code",
    "target_id",
    "product_class",
    "aoi",
    "layer_kind",
    "layer_name",
    "event_type",
    "obj_desc",
    "det_method",
    "notation",
    "dmg_src_id",
    "acq_datetime",
    "acq_window_start",
    "acq_window_end",
    "acq_precision",
    "acq_method",
    "delivery_time",
    "attrs_json",
    "geometry",
]


def _norm(name: str) -> str:
    return Path(name).name.casefold()


# era-A AOI layers: ..._AOI.shp / ..._AOI1_DTL3.shp (suffix only; a bare
# "_aoi" substring would match the _AOInn_ in every modern basename)
_ERA_A_AOI = re.compile(r"_aoi\d*(_dtl\d+)?\.shp$")


def classify_layer(shp_name: str) -> tuple[str, str] | None:
    """(table, kind/role) for a shapefile inside a product zip, else None."""
    n = _norm(shp_name)
    for pat, kind in common.SUPPLEMENTARY_LAYERS.items():
        if pat in n:
            return ("observed_event", kind)
    if any(p in n for p in common.EXTENT_PATTERNS):
        return ("observed_event", "observed")
    for pat, role in common.COVERAGE_LAYERS.items():
        if pat in n:
            return ("coverage", role)
    if _ERA_A_AOI.search(n):
        return ("coverage", "aoi")
    return None


def read_layer(zf: zipfile.ZipFile, shp_member: str) -> gpd.GeoDataFrame:
    """Extract one shapefile's sidecars to a tempdir and read+reproject it."""
    stem = shp_member[:-4]
    with tempfile.TemporaryDirectory() as td:
        for ext in SHP_PARTS:
            if stem + ext in zf.namelist():
                (Path(td) / f"layer{ext}").write_bytes(zf.read(stem + ext))
        g = gpd.read_file(Path(td) / "layer.shp")
    if g.crs is None:
        raise ValueError(f"{shp_member}: no CRS (.prj missing)")
    return g.to_crs("EPSG:4326")


def _get(props: dict, *names: str):
    """Case-insensitive attribute lookup across era naming styles."""
    low = {k.casefold(): v for k, v in props.items()}
    for n in names:
        v = low.get(n)
        if v is not None and v == v:  # not None, not NaN
            return v
    return None


def acq_from_attributes(props: dict) -> dict | None:
    """Era A/B: per-feature src_date (+ time inside src_info when present)."""
    src_date = _get(props, "src_date")
    if src_date is None:
        return None
    ts = pd.to_datetime(str(src_date), errors="coerce")
    # 1899-12-30 (and kin) is the ESRI null-date placeholder; CEMS Rapid
    # Mapping starts 2012 — implausible dates fall back to the window
    if pd.isna(ts) or ts.year < 2011:
        return None
    m = _SRC_INFO_DT.search(str(_get(props, "src_info") or ""))
    if m:
        d, mo, y, hh, mm = (int(x) for x in m.groups())
        return {
            "acq_datetime": pd.Timestamp(y, mo, d, hh, mm),
            "acq_precision": "minute",
            "acq_method": "attribute",
        }
    return {"acq_datetime": ts, "acq_precision": "date", "acq_method": "attribute"}


def acq_from_api(images: list[dict]) -> dict | None:
    times = sorted(pd.to_datetime(i["acquisitionTime"]) for i in images if i.get("acquisitionTime"))
    if not times:
        return None
    if len(times) == 1:
        return {"acq_datetime": times[0], "acq_precision": "minute", "acq_method": "api"}
    return {
        "acq_window_start": times[0],
        "acq_window_end": times[-1],
        "acq_precision": "window",
        "acq_method": "api_window",
    }


def fetch_api_images(code: str) -> tuple[dict, list[dict]]:
    """New-portal activation detail -> {(aoi_number, TYPE, monit): images},
    plus sources-table rows. Empty for legacy codes (backend 403s them)."""
    try:
        act = lens.cems.get_activation(code)
    except Exception:  # noqa: BLE001 — legacy codes are not on this backend
        return {}, []
    by_product, rows = {}, []
    for aoi in act.get("aois", []):
        for p in aoi.get("products", []):
            key = (p.get("aoiNumber"), p.get("type"), p.get("monitoringNumber"))
            imgs = p.get("images") or []
            by_product[key] = imgs
            rows += [
                {
                    "code": code,
                    "aoi_number": p.get("aoiNumber"),
                    "product_class": p.get("type"),
                    "monitoring_number": p.get("monitoringNumber"),
                    "sensor": i.get("sensorName"),
                    "sensor_type": i.get("sensorType"),
                    "acq_datetime": i.get("acquisitionTime"),
                    "file_name": i.get("fileName"),
                }
                for i in imgs
            ]
    return by_product, rows


def _api_key_from_basename(basename: str) -> tuple | None:
    """EMSR927_AOI03_GRA_MONIT01_v1.zip -> (3, 'GRA', 1); PRODUCT -> monit 0."""
    m = re.match(r"EMSR\d+_AOI(\d+)_([A-Z]{3})_(PRODUCT|MONIT(\d+))", basename)
    if not m:
        return None
    return (int(m.group(1)), m.group(2), int(m.group(4) or 0))


def process_zip(row: pd.Series, data: bytes, api_images: dict) -> dict[str, list]:
    """One bronze zip -> rows for observed_event and coverage."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    out: dict[str, list] = {"observed_event": [], "coverage": []}
    window = {
        "acq_window_start": row.get("event_time"),
        "acq_window_end": row["delivery_time"],
        "acq_precision": "window",
        "acq_method": "window",
    }
    api_acq = None
    if row["source"] == "new_portal":
        key = _api_key_from_basename(row["basename"])
        if key in api_images:
            api_acq = acq_from_api(api_images[key])

    for member in zf.namelist():
        if not member.casefold().endswith(".shp"):
            continue
        cls = classify_layer(member)
        if cls is None:
            continue
        table, kind = cls
        g = read_layer(zf, member)
        base = {
            "code": row["code"],
            "target_id": row["target_id"],
            "product_class": row["product_class"],
            "aoi": row["aoi"],
            "layer_name": Path(member).name,
            "delivery_time": row["delivery_time"],
        }
        for _, feat in g.iterrows():
            props = {k: v for k, v in feat.items() if k != "geometry"}
            rec = base | {"geometry": feat.geometry, "attrs_json": json.dumps(props, default=str)}
            if table == "coverage":
                rec |= {"role": kind, "or_src_id": _get(props, "or_src_id")}
            else:
                acq = acq_from_attributes(props) or api_acq or window
                rec |= {
                    "layer_kind": kind,
                    # prefer descriptive fields; era A also carries numeric codes
                    "event_type": _get(props, "event_type", "sbtypdes", "subtype", "evnt_type"),
                    "obj_desc": _get(props, "obj_desc", "interpret", "nam"),
                    "det_method": _get(props, "det_method"),
                    "notation": _get(props, "notation", "grading"),
                    "dmg_src_id": _get(props, "dmg_src_id"),
                    "acq_datetime": None,
                    "acq_window_start": None,
                    "acq_window_end": None,
                } | acq
            out[table].append(rec)
    return out


def write_table(fs, code: str, table: str, rows: list, cols: list | None = None) -> int:
    if not rows:
        # schema-only partition: "this code has zero rows" is a result, and
        # resume needs the partition to exist to see the code as complete
        g = gpd.GeoDataFrame(columns=cols or ["geometry"], geometry="geometry", crs="EPSG:4326")
        buf = io.BytesIO()
        g.to_parquet(buf, compression="zstd")
        blobio.upload(fs, buf.getvalue(), f"{SILVER}/{table}/code={code}/data.parquet")
        return 0
    g = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    if cols:
        g = g.reindex(columns=cols)
    for c in ("acq_datetime", "acq_window_start", "acq_window_end", "delivery_time"):
        if c in g:
            g[c] = pd.to_datetime(g[c], errors="raise")
    # canonical text fields can mix ints and strings across eras (raw codes
    # live untouched in attrs_json); parquet needs one type
    for c in ("event_type", "obj_desc", "det_method", "notation", "dmg_src_id", "or_src_id"):
        if c in g:
            g[c] = g[c].map(lambda v: None if v is None or v != v else str(v))
    buf = io.BytesIO()
    g.to_parquet(buf, compression="zstd")
    blobio.upload(fs, buf.getvalue(), f"{SILVER}/{table}/code={code}/data.parquet")
    return len(g)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", default="/tmp/gie_cems_flood_archive", type=Path)
    ap.add_argument("--stage", default="dev", choices=["dev", "prod"])
    ap.add_argument("--codes", default=None, help="comma-separated subset, e.g. EMSR009,EMSR927")
    ap.add_argument("--limit", type=int, default=None, help="max activations")
    ap.add_argument("--force", action="store_true", help="reprocess codes already in silver")
    args = ap.parse_args(argv)

    import ocha_stratus as stratus

    ledger = pd.read_parquet(args.work_dir / "products.parquet")
    acts = pd.read_parquet(args.work_dir / "activations.parquet")
    ledger = ledger.merge(
        acts[["code", "activationTime"]].rename(columns={"activationTime": "event_time"}),
        on="code",
        how="left",
    )
    up = ledger[ledger["status"] == "uploaded"]
    codes = sorted(up["code"].unique())
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",")]
    if args.limit:
        codes = codes[: args.limit]

    cc = stratus.get_container_client(container_name=common.CONTAINER, stage=args.stage)
    fs = blobio.uploader(common.global_settings(args.stage))

    if not args.codes and not args.force:
        # resume: skip codes with BOTH partitions present; a code killed
        # mid-write has observed_event but not coverage yet, so it gets redone
        def done_codes(table: str) -> set[str]:
            return {
                b.name.split("code=")[1].split("/")[0]
                for b in cc.list_blobs(name_starts_with=f"{SILVER}/{table}/code=")
            }

        complete = done_codes("observed_event") & done_codes("coverage")
        skipped = [c for c in codes if c in complete]
        codes = [c for c in codes if c not in complete]
        print(f"resume: {len(skipped)} codes already in silver, {len(codes)} to process")

    proc_rows = []
    for ci, code in enumerate(codes):
        targets = up[up["code"] == code]
        api_images, source_rows = fetch_api_images(code)
        tables: dict[str, list] = {"observed_event": [], "coverage": []}
        for _, row in targets.iterrows():
            rec = {"code": code, "target_id": row["target_id"], "processed_at": _now()}
            try:
                data = cc.download_blob(row["blob_path"]).readall()
                got = process_zip(row, data, api_images)
            except Exception as e:  # noqa: BLE001 — recorded per zip, visible in ledger
                proc_rows.append(rec | {"status": "error", "error": repr(e)[:300]})
                print(f"  ERROR {row['target_id']}: {e!r:.120}")
                continue
            n_ext = len(got["observed_event"])
            tables["observed_event"] += got["observed_event"]
            tables["coverage"] += got["coverage"]
            proc_rows.append(
                rec
                | {
                    "status": "ok" if n_ext else "no_extent_layer",
                    "n_extent": n_ext,
                    "n_coverage": len(got["coverage"]),
                }
            )
        n_e = write_table(fs, code, "observed_event", tables["observed_event"], EXTENT_COLS)
        n_c = write_table(fs, code, "coverage", tables["coverage"])
        if source_rows:
            src = pd.DataFrame(source_rows)
            src["acq_datetime"] = pd.to_datetime(src["acq_datetime"], errors="raise")
            buf = io.BytesIO()
            src.to_parquet(buf, compression="zstd")
            blobio.upload(fs, buf.getvalue(), f"{SILVER}/sources/code={code}/data.parquet")
        print(
            f"[{ci + 1}/{len(codes)}] {code}: extent={n_e} coverage={n_c} "
            f"api_images={sum(len(v) for v in api_images.values())}",
            flush=True,
        )
        if (ci + 1) % 10 == 0:  # ledger checkpoint: survive kills mid-run
            save_proc(args.work_dir, fs, proc_rows)

    proc = save_proc(args.work_dir, fs, proc_rows)
    print("\nprocessing ledger:")
    print(proc["status"].value_counts().to_string())


def save_proc(work: Path, fs, proc_rows: list[dict]) -> pd.DataFrame:
    """Merge this run's rows onto the existing processing ledger (idempotent
    per code) and persist locally + to blob."""
    proc = pd.DataFrame(proc_rows)
    path = work / "silver_processing.parquet"
    if path.exists():
        old = pd.read_parquet(path)
        done = proc["code"].unique() if len(proc) else []
        proc = pd.concat([old[~old["code"].isin(done)], proc], ignore_index=True)
    proc.to_parquet(path)
    buf = io.BytesIO()
    proc.to_parquet(buf)
    blobio.upload(fs, buf.getvalue(), f"{SILVER}/_meta/processing.parquet")
    return proc


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


if __name__ == "__main__":
    main()
