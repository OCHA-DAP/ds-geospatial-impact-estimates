"""Local mirroring of blob inputs for heavy DuckDB jobs.

DuckDB's azure-extension read intermittently *stalls* on large sustained scans
over this endpoint, and the read has no timeout, so it hangs at 0% CPU forever
(see harmonize_common / docs/handoff-sar.md). The Azure SDK download (stratus)
is robust here, so heavy jobs pull their inputs to local disk and let DuckDB
read local files. Writes are atomic (temp file + rename) and the cached base
set is verified against blob before use, so a partial cache fails loud rather
than silently serving a subset.
"""

from __future__ import annotations

import glob as _glob
import os
import threading
import time

import ocha_stratus as stratus


def fetch(blob: str, dst: str, settings, stage: str, tries: int = 10, timeout_s: int = 45) -> None:
    """Download one blob to dst with a per-file timeout + retry. The endpoint is
    stalling sustained transfers, so abandon a stalled fetch and retry it in a
    fresh window rather than hanging at 0% CPU forever."""
    for attempt in range(tries):
        result: dict = {}

        def _do(result=result):
            try:
                result["data"] = stratus.load_blob_data(
                    blob, stage=stage, container_name=settings.container
                )
            except Exception as e:  # noqa: BLE001
                result["err"] = e

        th = threading.Thread(target=_do, daemon=True)
        th.start()
        th.join(timeout_s)
        if "data" in result:
            tmp = f"{dst}.tmp"  # atomic write: temp file then rename, so an interrupted
            with open(tmp, "wb") as f:  # write can never leave a truncated file that a later
                f.write(result["data"])  # run skips-as-present and reads as complete.
            os.replace(tmp, dst)
            return
        reason = "stalled" if th.is_alive() else str(result.get("err", ""))[:40]
        print(f"    {os.path.basename(dst)} retry {attempt + 1}/{tries} ({reason})", flush=True)
        time.sleep(2)
    raise RuntimeError(f"download failed after {tries} tries: {blob}")


def local(
    settings, layer, *parts, event: str | None, stage: str, root: str = "/tmp/gie_local"
) -> str:
    """Download a single input blob to local and return its path (DuckDB then
    reads locally). ALWAYS re-fetched, never cached: these silver / codab inputs
    are small and change between runs, so caching them would serve stale data
    (only the large, stable Overture base is cached — see local_base)."""
    bp = settings.blob_path(layer, *parts, event=event)
    dst = os.path.join(root, bp)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    fetch(bp, dst, settings, stage)
    return dst


def local_base(settings, prefix: str, root: str, stage: str) -> str:
    """Download an Overture base tree (region=*/part-*.parquet under ``prefix``)
    to ``root`` once (cached), verify completeness, return a hive glob path.

    Use a DISTINCT root per event — the cache is keyed only by relative path,
    so two events sharing a root would silently mix their bases."""
    blobs = [
        b
        for b in stratus.list_container_blobs(
            name_starts_with=prefix, stage=stage, container_name=settings.container
        )
        if b.endswith(".parquet")
    ]
    if not blobs:
        raise RuntimeError(f"no Overture base parquets under {prefix} — run ingest_overture first")
    n = 0
    for b in blobs:
        rel = b[len(prefix) + 1 :]  # e.g. region=aragua/part-0.parquet
        dst = os.path.join(root, rel)
        if os.path.exists(dst):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        fetch(b, dst, settings, stage)
        n += 1
    have = {
        os.path.relpath(p, root) for p in _glob.glob(os.path.join(root, "region=*", "*.parquet"))
    }
    missing = {b[len(prefix) + 1 :] for b in blobs} - have
    if missing:  # a partial cache must fail loud, never be read as the whole base
        raise RuntimeError(
            f"Overture base cache incomplete: {len(missing)}/{len(blobs)} region files "
            f"missing (e.g. {sorted(missing)[:3]}). Delete {root} and re-run."
        )
    print(f"  base: {len(blobs)} region files local ({n} newly downloaded)", flush=True)
    return os.path.join(root, "region=*", "*.parquet")
