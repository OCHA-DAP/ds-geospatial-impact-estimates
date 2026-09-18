"""Transfer resources from the ledger into content-addressed bronze (spec §2).

Worker model: ``process_target`` is a pure function of one ledger row — it
downloads (streaming, hashing as it goes), tests the zip, inventories members,
and uploads unless the content already exists in bronze. It returns ledger
updates; it never touches the ledger, journal or checkpoints (main thread
only). Only the enumerated upstream outcomes become recorded statuses; bugs
propagate.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

from gie.unosat import cache, common
from gie.unosat.store import BlobStore

_CHUNK = 1 << 20  # 1 MiB
_TIMEOUT = 300

META_FILES = ("datasets.parquet", "resources.parquet", "zip_contents.parquet")
CHECKPOINT_EVERY = 25


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class DownloadResult:
    status_code: int
    sha256: str | None
    size: int


def stream_download(session, url: str, dest: Path, limiter: common.HostLimiter) -> DownloadResult:
    """GET ``url`` to ``dest`` in chunks, hashing in the same pass. A non-200
    writes nothing and returns the status. Network errors propagate."""
    h = hashlib.sha256()
    size = 0
    with limiter.acquire(url), session.get(url, stream=True, timeout=_TIMEOUT) as r:
        if r.status_code != 200:
            return DownloadResult(r.status_code, None, 0)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            for chunk in r.iter_content(_CHUNK):
                f.write(chunk)
                h.update(chunk)
                size += len(chunk)
    return DownloadResult(200, h.hexdigest(), size)


def inspect_zip(path: Path) -> list[zipfile.ZipInfo]:
    """Member list, or raise BadZipFile (also for a corrupt member)."""
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise zipfile.BadZipFile(f"corrupt member {bad}")
        return zf.infolist()


def member_rows(row: pd.Series, sha256: str, infos: list[zipfile.ZipInfo]) -> list[dict]:
    return [
        {
            "target_id": row["target_id"],
            "sha256": sha256,
            "event_code": row["event_code"],
            "member": i.filename,
            "file_size": i.file_size,
            "compress_size": i.compress_size,
        }
        for i in infos
    ]


def process_target(
    row: pd.Series,
    *,
    session,
    store: BlobStore,
    limiter: common.HostLimiter,
    use_cache: bool = True,
) -> tuple[dict, list[dict]]:
    """One ledger row -> (ledger updates, member inventory rows)."""
    prev = row["attempts"]
    attempts = (int(prev) if pd.notna(prev) else 0) + 1
    updates: dict = {"attempts": attempts, "attempted_at": _now()}
    basename = row["resource_name"]
    tmpdir = Path(tempfile.mkdtemp(prefix="unosat_"))
    tmp = tmpdir / basename
    try:
        try:
            dl = stream_download(session, row["url"], tmp, limiter)
        except requests.RequestException as e:
            err = f"{type(e).__name__}: {e}"[:300]
            return updates | {"status": "failed_download", "error": err}, []
        if dl.status_code == 404:
            return updates | {
                "status": "unavailable_404",
                "http_status": 404,
                "error": "HTTP 404",
            }, []
        if dl.status_code != 200:
            return updates | {
                "status": "failed_download",
                "http_status": dl.status_code,
                "error": f"HTTP {dl.status_code}",
            }, []
        try:
            infos = inspect_zip(tmp)
        except zipfile.BadZipFile as e:
            return updates | {
                "status": "corrupt_upstream",
                "http_status": 200,
                "error": f"BadZipFile: {e}",
                "size_bytes": dl.size,
            }, []
        sha = dl.sha256
        members = member_rows(row, sha, infos)
        dest = common.blob_path(sha, basename)
        base = updates | {
            "http_status": 200,
            "error": None,
            "sha256": sha,
            "size_bytes": dl.size,
            "n_members": len(infos),
        }
        if use_cache:
            final = cache.cache_path(sha, basename)
            final.parent.mkdir(parents=True, exist_ok=True)
            if not final.exists():
                shutil.move(tmp, final)
            tmp = final
        existing = store.exists_size(dest)
        if existing == dl.size:
            return base | {"status": "uploaded_dedup", "uploaded_at": _now()}, members
        try:
            store.upload(dest, tmp.read_bytes())
        except Exception as e:  # noqa: BLE001 — recorded as failed_upload, retryable, visible
            if store.exists_size(dest) == dl.size:
                # A concurrent writer won the race to this content-addressed path
                # while our upload failed; the bytes are identical by construction
                # (same sha256), so this is a dedup, not a failure.
                won = {"status": "uploaded_dedup", "uploaded_at": _now(), "error": None}
                return base | won, members
            return base | {"status": "failed_upload", "error": repr(e)[:300]}, []
        return base | {"status": "uploaded", "uploaded_at": _now()}, members
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def reconcile_with_blob(ledger: pd.DataFrame, store: BlobStore) -> pd.DataFrame:
    """Blob listing is truth. Rows that carry a sha256 are checked against the
    census: present with matching size -> uploaded; uploaded-in-ledger but
    absent or wrong size -> pending (loudly). Rows without a sha256 (never
    downloaded) and terminal rows are untouched."""
    sizes = store.list_sizes(f"{common.BRONZE}/blob=")
    has_sha = ledger["sha256"].notna()
    expected = ledger.loc[has_sha].apply(
        lambda r: common.blob_path(r["sha256"], r["resource_name"]), axis=1
    )
    got = expected.map(sizes.get)
    in_blob = got.notna()
    size_ok = in_blob & (got == ledger.loc[has_sha, "size_bytes"].astype("float"))
    status = ledger.loc[has_sha, "status"]

    already_settled = status.isin(common.UPLOADED_STATUSES) | status.isin(common.TERMINAL_STATUSES)
    to_mark = size_ok & ~already_settled
    if to_mark.any():
        ids = to_mark[to_mark].index
        print(f"reconcile: {len(ids)} targets already in blob -> uploaded")
        ledger.loc[ids, "status"] = "uploaded"
        ledger.loc[ids, "error"] = "reconciled: found in blob"

    demote = status.isin(common.UPLOADED_STATUSES) & ~size_ok
    if demote.any():
        ids = demote[demote].index
        print(
            f"WARNING reconcile: {len(ids)} ledger rows say uploaded but blob is missing "
            f"or has a different size -> pending: {list(ids)[:10]}{'...' if len(ids) > 10 else ''}"
        )
        ledger.loc[ids, "status"] = "pending"
        ledger.loc[ids, "error"] = "reconcile: blob missing/size mismatch"
    return ledger


def journal(work: Path, record: dict) -> None:
    with (work / "transfers.jsonl").open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def transfer_record(row: pd.Series, stage: str, outcome: str, **extra) -> dict:
    """Attempt record; field names follow this repo's data_transfers.jsonl."""
    sha = extra.get("sha256") or row.get("sha256")
    return {
        "ts": _now(),
        "outcome": outcome,
        "target_id": row["target_id"],
        "source": "unosat",
        "category": "reference",
        "dataset": f"UNOSAT {row.get('event_code') or row.get('dataset_name')} {row.get('format')}",
        "provider": common.PROVIDER,
        "licence": row.get("licence"),
        "origin_url": row["url"],
        "host": row.get("host"),
        "blob_path": common.blob_path(sha, row["resource_name"]) if sha else None,
        "stage": stage,
    } | extra


def checkpoint(
    work: Path, ledger: pd.DataFrame, members: list[dict], store: BlobStore
) -> list[dict]:
    """Persist ledger + member inventory + journal, locally and to blob _meta."""
    ledger.reset_index(drop=True).to_parquet(work / "resources.parquet")
    contents_path = work / "zip_contents.parquet"
    if members:
        new = pd.DataFrame(members)
        if contents_path.exists():
            old = pd.read_parquet(contents_path)
            old = old[~old["target_id"].isin(new["target_id"].unique())]
            new = pd.concat([old, new], ignore_index=True)
        new.to_parquet(contents_path)
    for name in META_FILES + ("transfers.jsonl",):
        p = work / name
        if p.exists():
            store.upload(f"{common.META}/{name}", p.read_bytes())
    return []


def apply_updates(ledger: pd.DataFrame, target_id, updates: dict) -> None:
    """Write ``process_target``'s updates onto ``ledger`` in place. On the
    network-exception branch ``process_target`` omits ``http_status``,
    which would otherwise leave a stale value from an earlier attempt on
    the same row; clear it explicitly for any recorded retryable/terminal
    outcome that doesn't supply its own."""
    for col, val in updates.items():
        ledger.loc[target_id, col] = val
    if (
        updates["status"] in (common.RETRYABLE_STATUSES | common.TERMINAL_STATUSES)
        and "http_status" not in updates
    ):
        ledger.loc[target_id, "http_status"] = pd.NA
