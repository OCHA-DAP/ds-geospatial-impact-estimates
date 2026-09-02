"""Gold: the two-table label system for ML consumers, built from silver.

  gold/label_index.parquet          one file, NO geometry. One row per
      (code, aoi, acquisition interval): bbox as numbers, dissolved area,
      sensor/method/precision ingredients, label_day when the interval fits
      one calendar day. The sampling catalog: filter/stratify in pandas.
  gold/labels/code=EMSRnnn/data.parquet   GeoParquet payload, same keys.
      Per row ONE dissolved flood geometry (observed extent) and ONE valid
      mask (image footprint minus not-analysed; falls back to the AOI
      polygon, stated in valid_basis). Rasterize both in the dataloader;
      pixels outside the valid mask are unobserved, not dry.

Grain: one row per distinct (aoi, acq_start, acq_end) among layer_kind ==
"observed" rows, i.e. per source observation. Exact rows have
acq_start == acq_end. Nothing is dropped: window rows keep label_day null
and stay filterable. Supplementary layers (modelled/max_extent/flood_depth)
are NOT labels and stay in silver.

Run:  uv run --group etl --group api python pipelines/cems_flood/gold.py
      [--codes ...] [--workers 4] [--stage dev]
"""

from __future__ import annotations

import argparse
import io
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import common
import geopandas as gpd
import pandas as pd

from gie import blobio

SILVER = "copernicus_ems/flood/silver"
GOLD = "copernicus_ems/flood/gold"
EQ_AREA = "EPSG:6933"

INDEX_COLS = [
    "code",
    "name",
    "countries",
    "aoi",
    "acq_start",
    "acq_end",
    "width_days",
    "label_day",
    "acq_method",
    "acq_precision",
    "sensor",
    "sensor_gsd",
    "det_methods",
    "product_classes",
    "n_polygons",
    "area_km2",
    "valid_basis",
    "valid_area_km2",
    "minx",
    "miny",
    "maxx",
    "maxy",
    "target_ids",
]


def _read(cc, table: str, code: str) -> gpd.GeoDataFrame:
    raw = cc.download_blob(f"{SILVER}/{table}/code={code}/data.parquet").readall()
    return gpd.read_parquet(io.BytesIO(raw))


def build_code(cc, fs, code: str, meta: dict) -> list[dict]:
    oe = _read(cc, "observed_event", code)
    cov = _read(cc, "coverage", code)
    obs = oe[oe.layer_kind == "observed"].copy()
    if not len(obs):
        return []

    obs["acq_start"] = pd.to_datetime(obs.acq_window_start.fillna(obs.acq_datetime))
    obs["acq_end"] = pd.to_datetime(obs.acq_window_end.fillna(obs.acq_datetime))
    # per-feature attribute dates can differ inside one product; the interval
    # grain keeps them apart, which is the point
    index_rows: list[dict] = []
    label_rows: list[dict] = []
    for (aoi, a0, a1), grp in obs.groupby(["aoi", "acq_start", "acq_end"], dropna=False):
        tids = sorted(grp.target_id.unique())
        flood = grp.geometry.union_all()
        c = cov[cov.target_id.isin(tids)]
        foot = c[c.role == "footprint"]
        nota = c[c.role == "not_analysed"]
        aoi_poly = c[c.role == "aoi"]
        # valid = (footprint INTERSECT aoi) MINUS not_analysed — same rule as
        # cems_coverage.py; CEMS analyses only inside the AOI, so an
        # unclipped satellite footprint would call vast outside areas "dry"
        aoi_geom = aoi_poly.geometry.union_all() if len(aoi_poly) else None
        if len(foot):
            valid = foot.geometry.union_all()
            basis = "footprint"
            if aoi_geom is not None:
                valid = valid.intersection(aoi_geom)
                basis = "footprint_x_aoi"
        elif aoi_geom is not None:
            valid = aoi_geom
            basis = "aoi"
        else:
            valid = None
            basis = "none"
        if valid is not None and len(nota):
            valid = valid.difference(nota.geometry.union_all())

        width = (a1 - a0).total_seconds() / 86400 if pd.notna(a0) and pd.notna(a1) else None
        label_day = (
            str(a0.date()) if pd.notna(a0) and pd.notna(a1) and a0.date() == a1.date() else None
        )
        area = gpd.GeoSeries([flood], crs="EPSG:4326").to_crs(EQ_AREA).area.iloc[0] / 1e6
        varea = (
            gpd.GeoSeries([valid], crs="EPSG:4326").to_crs(EQ_AREA).area.iloc[0] / 1e6
            if valid is not None
            else None
        )
        b = flood.bounds
        row = {
            "code": code,
            "name": meta.get("name"),
            "countries": meta.get("countries"),
            "aoi": aoi,
            "acq_start": a0,
            "acq_end": a1,
            "width_days": round(width, 3) if width is not None else None,
            "label_day": label_day,
            "acq_method": grp.acq_method.iloc[0],
            "acq_precision": grp.acq_precision.iloc[0],
            "sensor": None,
            "sensor_gsd": None,  # filled below where known
            "det_methods": "; ".join(sorted(grp.det_method.dropna().unique())),
            "product_classes": "; ".join(sorted(grp.product_class.unique())),
            "n_polygons": len(grp),
            "area_km2": round(float(area), 4),
            "valid_basis": basis,
            "valid_area_km2": round(float(varea), 2) if varea is not None else None,
            "minx": b[0],
            "miny": b[1],
            "maxx": b[2],
            "maxy": b[3],
            "target_ids": "; ".join(tids),
        }
        index_rows.append(row)
        label_rows.append(
            {k: row[k] for k in ("code", "aoi", "acq_start", "acq_end", "label_day")}
            | {"geometry": flood, "valid_geometry": valid, "valid_basis": basis}
        )

    # sensor per interval, from the sources package table where present
    try:
        sraw = cc.download_blob(f"{SILVER}/sources/code={code}/data.parquet").readall()
        src = pd.read_parquet(io.BytesIO(sraw))
        pkg = src[src.get("method") == "package"] if "method" in src else src.iloc[0:0]
        # key by (target_id, exact timestamp): two images can share a minute
        # across AOIs (EMSR871: TerraSAR-X and Sentinel-1 both at 16:49), so
        # neither date nor timestamp alone identifies the image
        import re as _re

        by_tt: dict = {}
        for r in pkg.itertuples():
            ts = pd.to_datetime(str(r.src_date), format="%d/%m/%Y", errors="coerce")
            if pd.isna(ts):
                continue
            m = _re.search(r"T?(\d{1,2}):(\d{2})", str(getattr(r, "source_tm", "") or ""))
            if m:
                ts = ts + pd.Timedelta(hours=int(m.group(1)), minutes=int(m.group(2)))
            by_tt[(r.target_id, ts)] = (str(r.source_nam), str(getattr(r, "sensor_gsd", "")))
        for row in index_rows:
            if row["acq_start"] != row["acq_end"]:
                continue
            for tid in row["target_ids"].split("; "):
                hit = by_tt.get((tid, row["acq_start"]))
                if hit:
                    row["sensor"], row["sensor_gsd"] = hit
                    break
    except Exception:  # noqa: BLE001 — no sources partition (era A/B)
        pass

    lab = gpd.GeoDataFrame(label_rows, geometry="geometry", crs="EPSG:4326")
    lab["valid_geometry"] = gpd.GeoSeries(lab["valid_geometry"], crs="EPSG:4326")
    buf = io.BytesIO()
    lab.to_parquet(buf, compression="zstd")
    blobio.upload(fs, buf.getvalue(), f"{GOLD}/labels/code={code}/data.parquet")
    return index_rows


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", default="/tmp/gie_cems_flood_archive", type=Path)
    ap.add_argument("--stage", default="dev", choices=["dev", "prod"])
    ap.add_argument("--codes", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)

    import ocha_stratus as stratus

    cc = stratus.get_container_client(container_name=common.CONTAINER, stage=args.stage)
    fs = blobio.uploader(common.global_settings(args.stage))
    acts = pd.read_parquet(args.work_dir / "activations.parquet").set_index("code")
    codes = sorted(
        {
            b.name.split("code=")[1].split("/")[0]
            for b in cc.list_blobs(name_starts_with=f"{SILVER}/observed_event/code=")
        }
    )
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",")]
    if args.limit:
        codes = codes[: args.limit]

    lock = threading.Lock()
    all_rows: list[dict] = []
    done = 0

    def worker(code: str) -> tuple[str, int]:
        meta = acts.loc[code].to_dict() if code in acts.index else {}
        rows = build_code(cc, fs, code, meta)
        with lock:
            all_rows.extend(rows)
        return code, len(rows)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for fut in as_completed({ex.submit(worker, c) for c in codes}):
            code, n = fut.result()
            done += 1
            print(f"[{done}/{len(codes)}] {code}: {n} label sets", flush=True)

    idx = pd.DataFrame(all_rows).reindex(columns=INDEX_COLS)
    for c in ("acq_start", "acq_end"):
        idx[c] = pd.to_datetime(idx[c])
    idx = idx.sort_values(["code", "aoi", "acq_start"]).reset_index(drop=True)
    buf = io.BytesIO()
    idx.to_parquet(buf, compression="zstd")
    blobio.upload(fs, buf.getvalue(), f"{GOLD}/label_index.parquet")
    idx.to_parquet(args.work_dir / "label_index.parquet")
    print(
        f"\nlabel_index: {len(idx):,} rows "
        f"({idx.label_day.notna().sum():,} with label_day) -> {GOLD}/label_index.parquet"
    )
    print(f"processed at {datetime.now(UTC).isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
