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
            return base | {"status": "failed_upload", "error": repr(e)[:300]}, []
        return base | {"status": "uploaded", "uploaded_at": _now()}, members
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
