"""Coded-value domains from UNOSAT geodatabases (spec §2, `domains.py`).

Older layers store codes (Water_Class = 2) whose meaning lives only in the
GDB's domain tables, and the binding is PER LAYER AND FIELD: the same GDB
binds `Water_Class` on 2014 layers and `Water_Class2` on 2021 layers. We read
domains once per distinct GDB content with GDAL's OpenFileGDB driver through
the `ogrinfo -json` CLI (the venv has no osgeo bindings).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROWS_COLUMNS = ["sha256", "layer", "field", "domain_name", "code", "value"]
STATUS_COLUMNS = ["sha256", "status", "n_rows", "processed_at", "error"]


class OgrinfoError(RuntimeError):
    """ogrinfo could not be run, or failed on a given GDB."""


def ogrinfo_json(gdb_path: Path) -> dict:
    exe = shutil.which("ogrinfo")
    if exe is None:
        raise OgrinfoError("ogrinfo not found on PATH — install GDAL (brew install gdal)")
    proc = subprocess.run([exe, "-json", "-ro", str(gdb_path)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise OgrinfoError(f"ogrinfo failed on {gdb_path}: {proc.stderr.strip()[:500]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise OgrinfoError(
            f"ogrinfo on {gdb_path} returned non-JSON: {proc.stdout[:500]!r}"
        ) from e


def domain_rows(sha256: str, info: dict) -> list[dict]:
    doms = info.get("domains") or {}
    rows: list[dict] = []
    for layer in info.get("layers") or []:
        for field in layer.get("fields") or []:
            dname = field.get("domainName")
            if not dname or dname not in doms:
                continue
            coded = doms[dname].get("codedValues") or {}
            items = (
                coded.items()
                if isinstance(coded, dict)
                else ((c["code"], c["value"]) for c in coded)
            )
            for code, value in items:
                rows.append(
                    {
                        "sha256": sha256,
                        "layer": layer["name"],
                        "field": field["name"],
                        "domain_name": dname,
                        "code": str(code),
                        "value": value,
                    }
                )
    return rows


def domains_for_gdb_zip(sha256: str, zip_path: Path) -> tuple[list[dict], str, str | None]:
    """Extract the zip to a temp dir, run ogrinfo on each .gdb inside, collect rows.

    An unreadable GDB (ogrinfo cannot open it) is an upstream property of that
    archived object, not a bug in our code: it is recorded as ``gdb_unreadable``
    with the ogrinfo error text, not raised, so one bad geodatabase never kills
    the rest of the run. Likewise a zip that cannot even be opened/extracted
    (not a zip at all, or a compression method Python's zipfile cannot
    decompress — such objects exist in bronze as ``uploaded_untested``) is
    recorded as ``zip_unreadable``, not raised.
    """
    try:
        with zipfile.ZipFile(zip_path) as z:
            gdb_dirs = sorted(
                {n.split(".gdb/")[0] + ".gdb" for n in z.namelist() if ".gdb/" in n}
            )
            if not gdb_dirs:
                return [], "no_gdb_in_zip", None
            tmp = Path(tempfile.mkdtemp(prefix="unosat_gdb_"))
            try:
                z.extractall(tmp)
                rows: list[dict] = []
                errors: list[tuple[str, str]] = []
                for g in gdb_dirs:
                    try:
                        rows.extend(domain_rows(sha256, ogrinfo_json(tmp / g)))
                    except OgrinfoError as e:
                        errors.append((g, str(e)[:500]))
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    except (zipfile.BadZipFile, NotImplementedError) as e:
        return [], "zip_unreadable", f"{type(e).__name__}: {e}"[:500]
    if errors:
        error = "; ".join(f"{g}: {err}" for g, err in errors)[:500]
        return rows, "gdb_unreadable", error
    return rows, ("ok" if rows else "no_domains"), None


def status_row(sha256: str, status: str, n_rows: int, error: str | None = None) -> dict:
    return {
        "sha256": sha256,
        "status": status,
        "n_rows": n_rows,
        "processed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "error": error,
    }


def persist(work_dir: Path, new_rows: list[dict], new_status: list[dict]) -> None:
    """Merge ``new_rows``/``new_status`` into the two parquet files under
    ``work_dir``, replacing any existing rows/status for the sha256 values in
    ``new_status``. Rows are written BEFORE status, deliberately: a crash
    between the two writes leaves those sha256 values without a status row,
    so the next run's resume filter treats them as not-yet-done and simply
    redoes and replaces them — never silently skips work whose rows never
    landed."""
    done = {s["sha256"] for s in new_status}

    rows_path = work_dir / "domains.parquet"
    old_rows = (
        pd.read_parquet(rows_path) if rows_path.exists() else pd.DataFrame(columns=ROWS_COLUMNS)
    )
    old_rows = old_rows[~old_rows["sha256"].isin(done)]
    rows = pd.concat([old_rows, pd.DataFrame(new_rows, columns=ROWS_COLUMNS)], ignore_index=True)
    rows[ROWS_COLUMNS].to_parquet(rows_path)

    status_path = work_dir / "domains_status.parquet"
    old_status = (
        pd.read_parquet(status_path).reindex(columns=STATUS_COLUMNS)
        if status_path.exists()
        else pd.DataFrame(columns=STATUS_COLUMNS)
    )
    old_status = old_status[~old_status["sha256"].isin(done)]
    status = pd.concat(
        [old_status, pd.DataFrame(new_status, columns=STATUS_COLUMNS)], ignore_index=True
    )
    status[STATUS_COLUMNS].to_parquet(status_path)
