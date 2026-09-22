"""Inventory of every layer inside every archived flood/cyclone zip (spec §3 prerequisite).

GDB feature classes come from `ogrinfo -json` (name, geometry type, feature count, fields and
their domain bindings); SHP members from the bronze zip inventory. This table is what the layer
grammar is tested against and what silver iterates over.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

from gie.unosat import domains

LAYERS_COLUMNS = ["sha256", "zip_basename", "source", "layer", "geometry_type",
                  "feature_count", "fields", "field_domains"]
STATUS_COLUMNS = ["sha256", "status", "error"]


def layers_from_ogrinfo(sha256: str, zip_basename: str, info: dict) -> list[dict]:
    rows = []
    for lyr in info.get("layers") or []:
        gf = lyr.get("geometryFields") or []
        rows.append({
            "sha256": sha256, "zip_basename": zip_basename, "source": "gdb",
            "layer": lyr["name"],
            "geometry_type": gf[0].get("type") if gf else None,
            "feature_count": lyr.get("featureCount"),
            "fields": [f["name"] for f in lyr.get("fields") or []],
            "field_domains": {
                f["name"]: f["domainName"] for f in lyr.get("fields") or [] if f.get("domainName")
            },
        })
    return rows


def layers_from_zip_members(sha256: str, zip_basename: str, members: list[str]) -> list[dict]:
    return [{
        "sha256": sha256, "zip_basename": zip_basename, "source": "shp",
        "layer": m.split("/")[-1][:-4], "geometry_type": None, "feature_count": None,
        "fields": None, "field_domains": None,
    } for m in members if m.lower().endswith(".shp")]


def layers_for_gdb_zip(
    sha256: str, zip_basename: str, zip_path: Path
) -> tuple[list[dict], str, str | None]:
    """Mirror of ``domains.domains_for_gdb_zip``: extract every ``.gdb`` in the
    zip via ``domains.extract_gdbs``, run ogrinfo on each, and turn its layers
    into rows via ``layers_from_ogrinfo``.

    An unreadable GDB is recorded as ``gdb_unreadable`` with the ogrinfo error
    text (rows from any other readable GDB in the same zip are kept, not
    discarded), never raised — one bad geodatabase must not kill the rest of
    the run. A zip Python's zipfile cannot open or decompress is recorded as
    ``zip_unreadable``. A zip with no ``.gdb`` inside it, or whose readable
    GDBs list no layers at all, is ``no_layers`` — content absence, not an
    error.
    """
    try:
        with domains.extract_gdbs(zip_path) as gdb_paths:
            if not gdb_paths:
                return [], "no_layers", None
            rows: list[dict] = []
            errors: list[tuple[str, str]] = []
            for g in gdb_paths:
                try:
                    rows.extend(layers_from_ogrinfo(sha256, zip_basename, domains.ogrinfo_json(g)))
                except domains.OgrinfoError as e:
                    errors.append((g.name, str(e)[:500]))
    except (zipfile.BadZipFile, NotImplementedError) as e:
        return [], "zip_unreadable", f"{type(e).__name__}: {e}"[:500]
    if errors:
        error = "; ".join(f"{g}: {err}" for g, err in errors)[:500]
        return rows, "gdb_unreadable", error
    return rows, ("ok" if rows else "no_layers"), None


def status_row(sha256: str, status: str, error: str | None = None) -> dict:
    return {"sha256": sha256, "status": status, "error": error}


def load_frames(work_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The two accumulated tables under ``work_dir``, reindexed to their
    schemas; a typed empty frame where the file does not exist yet."""
    frames = []
    specs = (("layers.parquet", LAYERS_COLUMNS), ("layers_status.parquet", STATUS_COLUMNS))
    for name, columns in specs:
        path = work_dir / name
        frames.append(
            pd.read_parquet(path).reindex(columns=columns)
            if path.exists()
            else pd.DataFrame(columns=columns)
        )
    return frames[0], frames[1]


def merge_batch(
    rows_df: pd.DataFrame,
    status_df: pd.DataFrame,
    new_rows: list[dict],
    new_status: list[dict],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fold one batch into the accumulated tables: rows and status for the
    sha256 values in ``new_status`` are replaced, not appended to. Pure — it
    reads and writes nothing."""
    done = {s["sha256"] for s in new_status}
    rows = pd.concat(
        [rows_df[~rows_df["sha256"].isin(done)], pd.DataFrame(new_rows, columns=LAYERS_COLUMNS)],
        ignore_index=True,
    )
    status = pd.concat(
        [status_df[~status_df["sha256"].isin(done)],
         pd.DataFrame(new_status, columns=STATUS_COLUMNS)],
        ignore_index=True,
    )
    return rows[LAYERS_COLUMNS], status[STATUS_COLUMNS]


def persist_frames(work_dir: Path, rows_df: pd.DataFrame, status_df: pd.DataFrame) -> None:
    """Write both tables. Rows go BEFORE status, deliberately: a crash between
    the two writes leaves those sha256 values without a status row, so the next
    run's resume filter treats them as not-yet-done and simply redoes and
    replaces them — never silently skips work whose rows never landed."""
    rows_df.to_parquet(work_dir / "layers.parquet")
    status_df.to_parquet(work_dir / "layers_status.parquet")
