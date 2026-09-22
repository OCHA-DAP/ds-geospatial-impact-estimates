"""Shared plumbing for the UNOSAT archive (pipelines/unosat).

The archive lands in container ``global`` under ``unosat/`` because it is a
general historical corpus, not event-scoped project data (same reasoning as
the CEMS flood archive, ADR-0029). Bronze is content-addressed: one object
per distinct sha256, because HDX datasets are cumulative snapshots that
re-ship the same zip many times (spec §Decisions).
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import re
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import platformdirs
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from gie.config import Settings, load_settings

CONTAINER = "global"
BRONZE = "unosat/bronze"
META = f"{BRONZE}/_meta"
# What a bronze census lists: the content-addressed objects, not `_meta/`.
BLOB_LISTING_PREFIX = f"{BRONZE}/blob="
SILVER = "unosat/silver"
SILVER_META = f"{SILVER}/_meta"
GOLD = "unosat/gold"
USER_AGENT = "OCHA-CHD-DS unosat-archive (ds-geospatial-impact-estimates)"
PROVIDER = "United Nations Satellite Centre (UNOSAT), via HDX"

# Resource formats we archive. KMZ are map graphics: inventoried, not fetched.
HARVEST_FORMATS = ("SHP", "Geodatabase", "XLSX", "Geopackage")

# Upstream said no, permanently (stable across retries hours apart): never retried.
TERMINAL_STATUSES = frozenset({"unavailable_404", "corrupt_upstream"})
# Our side or transient upstream: retried only with --retry-failed.
RETRYABLE_STATUSES = frozenset({"failed_download", "failed_upload"})
UPLOADED_STATUSES = frozenset({"uploaded", "uploaded_dedup", "uploaded_untested"})

LEDGER_COLS = [
    "target_id",
    "dataset_id",
    "dataset_name",
    "resource_id",
    "resource_name",
    "format",
    "url",
    "host",
    "hdx_size",
    "hdx_hash",
    "last_modified",
    "event_code",
    "hazard_prefix",
    "iso3",
    "scope",
    "licence",
    "status",
    "http_status",
    "error",
    "attempts",
    "attempted_at",
    "uploaded_at",
    "sha256",
    "size_bytes",
    "n_members",
    "missing_upstream",
]

_EVENT_CODE = re.compile(r"^([A-Z]{2})(\d{8})([A-Z]{3})")


def parse_event_code(name: str) -> dict | None:
    """``FL20220424SSD_SHP.zip`` -> {event_code, hazard_prefix, iso3}; None if absent."""
    m = _EVENT_CODE.match(name or "")
    if not m:
        return None
    return {"event_code": m.group(0), "hazard_prefix": m.group(1), "iso3": m.group(3)}


def scope_for(prefix: str | None) -> str:
    if prefix is None:
        return "unknown"
    return "flood" if prefix in ("FL", "TC") else "other"


def blob_path(sha256: str, basename: str) -> str:
    return f"{BRONZE}/blob={sha256}/{basename}"


def host_of(url: str) -> str:
    return urlsplit(url).netloc


def default_work_dir() -> Path:
    """Where the ledger, journal and checkpoints live: ``$GIE_WORK_DIR`` if
    set, else ``platformdirs.user_data_dir("gie")/unosat_archive``. Off
    ``/tmp`` so the local work dir survives a reboot."""
    env = os.getenv("GIE_WORK_DIR")
    return Path(env) if env else Path(platformdirs.user_data_dir("gie")) / "unosat_archive"


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """The two arguments every unosat CLI takes, spelled once."""
    parser.add_argument("--work-dir", default=default_work_dir(), type=Path)
    parser.add_argument("--stage", default="dev", choices=["dev", "prod"])


def atomic_write(dest: Path, data: bytes) -> None:
    """Write ``data`` to ``dest`` via a temp file in the same directory and
    ``os.replace``, so a killed or failed write never leaves a truncated file
    at ``dest``. The temp file is removed and the failure re-raised, including
    on KeyboardInterrupt. ``dest.parent`` must exist."""
    fd, tmp_str = tempfile.mkstemp(dir=dest.parent, prefix=dest.name + ".", suffix=".part")
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
    except BaseException:
        if tmp.exists():
            tmp.unlink()
        raise


def global_settings(stage: str) -> Settings:
    """This repo's Settings pointed at the ``global`` container."""
    return dataclasses.replace(load_settings(stage), container=CONTAINER)


def coerce_ledger_dtypes(df):
    """Stabilize transfer-column dtypes (see cems_flood.common for the why:
    all-NaN columns come back from parquet as float64 and pandas >= 2 refuses
    string assignment into them)."""
    for col in ("attempted_at", "uploaded_at", "sha256", "error", "hdx_hash"):
        if col in df and not str(df[col].dtype).startswith(("object", "str")):
            df[col] = df[col].astype(object).where(df[col].notna(), None)
    for col in ("http_status", "attempts", "size_bytes", "n_members", "hdx_size"):
        if col in df:
            df[col] = df[col].astype("Int64")
    if "missing_upstream" in df:
        df["missing_upstream"] = df["missing_upstream"].fillna(False).astype(bool)
    return df


def make_session() -> requests.Session:
    """Polite session: our UA, retry/backoff on transient upstream errors only.
    404 is deliberately NOT in the forcelist: it is a terminal ledger state."""
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    retry = Retry(
        total=4,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


class HostLimiter:
    """Cap concurrent requests per host; five hosts share one worker pool."""

    def __init__(self, max_per_host: int = 3) -> None:
        self._max = max_per_host
        self._sems: dict[str, threading.Semaphore] = {}
        self._lock = threading.Lock()

    def _sem(self, host: str) -> threading.Semaphore:
        with self._lock:
            if host not in self._sems:
                self._sems[host] = threading.Semaphore(self._max)
            return self._sems[host]

    @contextmanager
    def acquire(self, url: str) -> Iterator[None]:
        sem = self._sem(host_of(url))
        sem.acquire()
        try:
            yield
        finally:
            sem.release()
