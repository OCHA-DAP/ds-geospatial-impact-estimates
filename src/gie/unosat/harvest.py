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
from azure.core.exceptions import AzureError

from gie.unosat import cache, common
from gie.unosat.store import BlobStore

_CHUNK = 1 << 20  # 1 MiB
_TIMEOUT = 300

META_FILES = ("datasets.parquet", "resources.parquet", "zip_contents.parquet")
CHECKPOINT_EVERY = 25

# What this attempt did: always present in every outcome, None where the
# branch has nothing to say. That is what lets ``apply_updates`` stay
# special-case-free and still clear a stale http_status from an earlier
# attempt on the same row.
STATE_KEYS = ("status", "http_status", "error", "attempts", "attempted_at")
# What this attempt learned about the bytes: present ONLY when this attempt
# learned it. A branch that never got bytes omits these rather than writing
# None, so a fingerprint learned by an earlier attempt survives a failed retry
# and ``reconcile_with_blob`` can still heal the row from the blob census.
CONTENT_KEYS = ("sha256", "size_bytes", "n_members", "uploaded_at")
OUTCOME_KEYS = STATE_KEYS + CONTENT_KEYS


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _outcome(**fields) -> dict:
    """Build an outcome dict: every ``STATE_KEYS`` entry (None where not
    given) plus whichever ``CONTENT_KEYS`` this attempt actually learned. An
    unknown field is a bug, not a new column."""
    unknown = sorted(set(fields) - set(OUTCOME_KEYS))
    if unknown:
        raise ValueError(f"not outcome keys: {unknown}")
    return {k: fields.get(k) for k in STATE_KEYS} | {
        k: v for k, v in fields.items() if k in CONTENT_KEYS
    }


def content_key(row) -> tuple[str, str]:
    """The identity of the content a ledger row points at: ``(url, size
    bucket)``.

    Two rows are the same content iff their URL AND their declared HDX size
    match. A row with no declared size gets the bucket ``"na"``, which matches
    only another undeclared size — never a row that declares one, because
    nothing then says the bytes are the same. This one rule is what both
    ``representatives`` (download once per distinct content) and
    ``settle_url_siblings`` (settle a pending row from an uploaded one) use.
    """
    size = row["hdx_size"]
    return row["url"], str(int(size)) if pd.notna(size) else "na"


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


def inspect_zip(path: Path) -> tuple[list[zipfile.ZipInfo], bool]:
    """Member list and whether ``testzip()`` actually verified them, or raise
    BadZipFile (also for a corrupt member). ``tested`` is False when the
    archive uses a compression method Python's zipfile cannot decompress
    (Deflate64, PPMd, ...): the zip itself is still valid and its members are
    still listed via ``infolist()``, they just could not be test-decompressed."""
    with zipfile.ZipFile(path) as zf:
        try:
            bad = zf.testzip()
        except NotImplementedError:
            return zf.infolist(), False
        if bad is not None:
            raise zipfile.BadZipFile(f"corrupt member {bad}")
        return zf.infolist(), True


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
    """One ledger row -> (ledger updates, member inventory rows).

    Every outcome carries all ``STATE_KEYS`` (status, http_status, error,
    attempts, attempted_at), None where this branch has nothing to say — so
    applying it clears a stale http_status without any special case. It
    carries a ``CONTENT_KEYS`` entry (sha256, size_bytes, n_members,
    uploaded_at) only when THIS attempt learned it: a branch that never got
    the bytes (failed_download, unavailable_404) omits them entirely, leaving
    whatever an earlier attempt learned in place, so a failed retry does not
    erase a fingerprint that ``reconcile_with_blob`` could still heal the row
    from. corrupt_upstream records size_bytes; failed_upload records sha256,
    size_bytes and n_members — both did get the bytes.
    """
    prev = row["attempts"]
    attempts = (int(prev) if pd.notna(prev) else 0) + 1
    attempted_at = _now()

    def outcome(**fields) -> dict:
        return _outcome(attempts=attempts, attempted_at=attempted_at, **fields)

    basename = row["resource_name"]
    tmpdir = Path(tempfile.mkdtemp(prefix="unosat_"))
    tmp = tmpdir / basename
    try:
        try:
            dl = stream_download(session, row["url"], tmp, limiter)
        except requests.RequestException as e:
            err = f"{type(e).__name__}: {e}"[:300]
            return outcome(status="failed_download", error=err), []
        if dl.status_code == 404:
            return outcome(status="unavailable_404", http_status=404, error="HTTP 404"), []
        if dl.status_code != 200:
            return outcome(
                status="failed_download",
                http_status=dl.status_code,
                error=f"HTTP {dl.status_code}",
            ), []
        try:
            infos, tested = inspect_zip(tmp)
        except zipfile.BadZipFile as e:
            return outcome(
                status="corrupt_upstream",
                http_status=200,
                error=f"BadZipFile: {e}",
                size_bytes=dl.size,
            ), []
        sha = dl.sha256
        members = member_rows(row, sha, infos)
        dest = common.blob_path(sha, basename)
        base = {
            "http_status": 200,
            "error": None if tested else "zip_test: unsupported compression method",
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
            return outcome(**base, status="uploaded_dedup", uploaded_at=_now()), members
        data = tmp.read_bytes()
        try:
            store.upload(dest, data)
        except (AzureError, OSError) as e:
            if store.exists_size(dest) == dl.size:
                # A concurrent writer won the race to this content-addressed path
                # while our upload failed; the bytes are identical by construction
                # (same sha256), so this is a dedup, not a failure. base's own
                # error (e.g. a zip_test note) stands; the upload error is not
                # recorded because nothing failed for this content.
                return outcome(**base, status="uploaded_dedup", uploaded_at=_now()), members
            return outcome(**base | {"error": repr(e)[:300]}, status="failed_upload"), []
        status = "uploaded" if tested else "uploaded_untested"
        return outcome(**base, status=status, uploaded_at=_now()), members
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def reconcile_with_blob(ledger: pd.DataFrame, store: BlobStore) -> pd.DataFrame:
    """Blob listing is truth. Rows that carry a sha256 are checked against the
    census: present with matching size -> uploaded; uploaded-in-ledger but
    absent or wrong size -> pending (loudly). Rows without a sha256 (never
    downloaded) and terminal rows are untouched."""
    sizes = store.list_sizes(common.BLOB_LISTING_PREFIX)
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


def settle_url_siblings(ledger: pd.DataFrame) -> list[tuple[str, dict]]:
    """Pending rows whose ``content_key`` already has an uploaded row (any
    ``UPLOADED_STATUSES``) become ``uploaded_dedup``, copying sha256,
    size_bytes, n_members, http_status=200, error=None, uploaded_at=now.
    Returns ``[(target_id, updates)]`` for the caller to apply + journal; does
    not mutate ``ledger``."""
    uploaded = ledger[ledger["status"].isin(common.UPLOADED_STATUSES)]
    donors: dict[tuple[str, str], pd.Series] = {}
    for _, row in uploaded.iterrows():
        donors.setdefault(content_key(row), row)
    now = _now()
    out: list[tuple[str, dict]] = []
    pending = ledger[ledger["status"] == "pending"]
    for _, row in pending.iterrows():
        src = donors.get(content_key(row))
        if src is None:
            continue
        out.append((
            row["target_id"],
            {
                "status": "uploaded_dedup",
                "sha256": src["sha256"],
                "size_bytes": src["size_bytes"],
                "n_members": src["n_members"],
                "http_status": 200,
                "error": None,
                "uploaded_at": now,
            },
        ))
    return out


def representatives(todo: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Group the ``todo`` frame by ``content_key``. Return (one row per group —
    the first by target_id —, mapping the representative's target_id -> list
    of the OTHER target_ids in its group)."""
    ordered = todo.reset_index(drop=True).sort_values("target_id").copy()
    ordered["_content_key"] = pd.Series(
        [content_key(row) for _, row in ordered.iterrows()], index=ordered.index, dtype=object
    )
    reps = ordered.drop_duplicates("_content_key", keep="first").drop(columns="_content_key")
    siblings = {
        group["target_id"].iloc[0]: group["target_id"].tolist()[1:]
        for _, group in ordered.groupby("_content_key", sort=False)
    }
    return reps, siblings


def sibling_updates(updates: dict, members: list[dict], sibling_id: str) -> tuple[dict, list[dict]]:
    """Derive a sibling row's (updates, member rows) from the representative's
    outcome. Success (uploaded / uploaded_untested / uploaded_dedup) ->
    sibling status uploaded_dedup with the same sha256, size_bytes, n_members,
    http_status, error, uploaded_at=now; member rows re-keyed to
    ``sibling_id``. Any failure or terminal status -> identical updates (same
    URL fails the same way). Either way ``attempts``/``attempted_at`` are
    dropped: no attempt was made for the sibling, and whichever content keys
    the representative's outcome carries are the ones the sibling gets."""
    sib_updates = {k: v for k, v in updates.items() if k not in ("attempts", "attempted_at")}
    if updates["status"] in common.UPLOADED_STATUSES:
        sib_updates |= {"status": "uploaded_dedup", "uploaded_at": _now()}
        sib_members = [{**m, "target_id": sibling_id} for m in members]
    else:
        sib_members = []
    return sib_updates, sib_members


def journal(work: Path, record: dict) -> None:
    with (work / "transfers.jsonl").open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def transfer_record(
    row: pd.Series, stage: str, outcome: str, *, via: str | None = None, **extra
) -> dict:
    """Attempt record; field names follow this repo's data_transfers.jsonl.
    ``via`` names how the outcome was reached when it wasn't a direct
    download attempt (e.g. ``"url_sibling"``)."""
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
        "via": via,
    } | extra


def record_outcome(
    ledger: pd.DataFrame,
    work_dir: Path,
    stage: str,
    target_id: str,
    updates: dict,
    members: list[dict],
    *,
    via: str | None = None,
) -> list[dict]:
    """Apply one outcome to the ledger and journal it — the single path by
    which any outcome is recorded, whether it came from a download attempt, a
    URL sibling or the settle step. Returns ``members`` unchanged, so the
    caller can accumulate them in one expression."""
    apply_updates(ledger, target_id, updates)
    journal(
        work_dir,
        transfer_record(
            ledger.loc[target_id], stage, updates["status"], via=via,
            size_bytes=updates.get("size_bytes"), sha256=updates.get("sha256"),
            error=updates.get("error"),
        ),
    )
    return members


def propagate_to_siblings(
    ledger: pd.DataFrame,
    work_dir: Path,
    stage: str,
    updates: dict,
    members: list[dict],
    sibling_ids: list[str],
) -> list[dict]:
    """Record the representative's outcome against each of its siblings (see
    ``sibling_updates``). Returns every sibling's member rows."""
    out: list[dict] = []
    for sibling_id in sibling_ids:
        sib_updates, sib_members = sibling_updates(updates, members, sibling_id)
        out.extend(
            record_outcome(
                ledger, work_dir, stage, sibling_id, sib_updates, sib_members, via="url_sibling"
            )
        )
    return out


def outcome_marker(updates: dict) -> str:
    """Progress-line marker for one outcome: the bare status when the content
    landed, ``** status: error`` when it did not."""
    status = updates["status"]
    return status if status in common.UPLOADED_STATUSES else f"** {status}: {updates.get('error')}"


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
    """Write an outcome onto ``ledger`` in place. Every key present is
    applied, None included: an outcome always carries ``STATE_KEYS``, so a
    branch with no http_status writes None and thereby clears a stale value
    from an earlier attempt. Keys the outcome omits — the ``CONTENT_KEYS`` an
    attempt that never got bytes cannot speak to — are left as they were."""
    for col, val in updates.items():
        ledger.loc[target_id, col] = val
