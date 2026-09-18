# UNOSAT Archive — Bronze (discovery, harvest, domains, audit) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Archive every UNOSAT product zip catalogued on HDX into a content-addressed bronze layer on blob, with a ledger that accounts for every resource (fetched, deduplicated, or explicitly unavailable), a local read-through cache, coded-value domains extracted from every geodatabase, and an audit that proves ledger and blob agree.

**Architecture:** Library code in `src/gie/unosat/` (importable, unit-tested), thin CLIs in `pipelines/unosat/` mirroring `pipelines/cems_flood/`. Discovery builds the ledger from the HDX CKAN API via `hdx-python-api`; harvest streams each resource to the local cache while hashing, tests the zip, and uploads one blob object per distinct sha256 via `gie.blobio`; domains reads every GDB once with `ogrinfo -json`; audit checks ledger-vs-blob invariants. Workers are pure download/upload; the ledger, journal and checkpoints are touched only in the main thread.

**Tech Stack:** Python 3.13 via `uv`, pandas, pyarrow, requests, `hdx-python-api`, `platformdirs`, `azure-storage-file-datalake` (through `gie.blobio`), `ocha-stratus` (blob listing/reads), GDAL `ogrinfo` CLI (Homebrew, 3.11 present), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-09-18-unosat-flood-archive-design.md` — read it fully first; sections 1, 2, 2b and 5 (B-rules) are what this plan implements. Silver and gold (spec §3–4) get their own plan once bronze exists.

## Global Constraints

- Work on branch `feat/unosat-archive` created from `docs/unosat-archive-spec` (which holds the spec). Commit after every task. **No `Co-Authored-By` or AI attribution lines in commits** (user rule).
- Run everything with `uv run --group etl --group api python ...` and tests with `uv run pytest tests/unosat -q`. Lint with `uv run ruff check src/gie/unosat pipelines/unosat tests/unosat` (line length 100, rules E F I UP B SIM).
- Blob: container `global`, stage `dev` by default (`--stage prod` only when promoting). Prefix `unosat/bronze/`. Object path `unosat/bronze/blob={sha256}/{basename}`. Metadata under `unosat/bronze/_meta/`.
- **Fail loudly.** Three states, never conflated: upstream absence (HTTP 404, HTTP 200 that is not a zip) → explicit terminal ledger status (`unavailable_404`, `corrupt_upstream`), never retried by `--retry-failed`; fetch/upload failure (network, 5xx after retries, upload error) → `failed_download` / `failed_upload`, visible, retried only with `--retry-failed`; empty content is not an error. No `try/except: continue`. Workers raise on bugs; only the enumerated upstream outcomes become recorded statuses.
- Ledger status vocabulary (exact strings): `pending`, `excluded_kmz`, `uploaded`, `uploaded_dedup`, `failed_download`, `failed_upload`, `unavailable_404`, `corrupt_upstream`.
- Politeness: 6 workers total, at most 3 concurrent requests per host, `User-Agent: OCHA-CHD-DS unosat-archive (ds-geospatial-impact-estimates)`, retry/backoff on 429/500/502/503/504.
- Local cache root: `GIE_CACHE_DIR` env var, else `platformdirs.user_cache_dir("gie")`. Layout mirrors bronze: `{root}/unosat/bronze/blob={sha256}/{basename}`. `--no-cache` disables writes.
- Work dir (ledger, journal, checkpoints): `--work-dir`, default `/tmp/gie_unosat_archive`.
- Never commit anything under `data/`, `*.parquet`, or the work dir (already gitignored).

## File Structure

```
src/gie/unosat/__init__.py          empty
src/gie/unosat/common.py            constants, event-code parsing, scope, ledger columns/dtypes,
                                    global_settings, polite session + per-host limiter
src/gie/unosat/cache.py             cache_root(), cache_path(), read_through()
src/gie/unosat/discovery.py         fetch_unosat_datasets(), resources_ledger(), merge_ledgers()
src/gie/unosat/store.py             BlobStore protocol, MemoryStore (tests), DataLakeStore (real)
src/gie/unosat/harvest.py           stream_download(), inspect_zip(), process_target(),
                                    reconcile_with_blob(), journal(), transfer_record(), checkpoint()
src/gie/unosat/domains.py           ogrinfo_json(), domain_rows(), domains_for_gdb_zip()
src/gie/unosat/audit.py             check_b1_no_pending(), check_b2_census(), check_b3_domains()
pipelines/unosat/discovery.py       CLI
pipelines/unosat/harvest.py         CLI (thread pool, main-thread ledger)
pipelines/unosat/domains.py         CLI
pipelines/unosat/audit.py           CLI
pipelines/unosat/README.md          ops
tests/unosat/__init__.py
tests/unosat/conftest.py            zip + ledger fixtures
tests/unosat/test_common.py
tests/unosat/test_cache.py
tests/unosat/test_discovery.py
tests/unosat/test_harvest.py
tests/unosat/test_domains.py
tests/unosat/test_audit.py
docs/decisions/0033-unosat-flood-archive-content-addressed-bronze.md
pyproject.toml                      add hdx-python-api, platformdirs to the etl group
```

---

### Task 1: Package scaffold, constants, event-code parsing, polite session

**Files:**
- Create: `src/gie/unosat/__init__.py`, `src/gie/unosat/common.py`
- Create: `tests/unosat/__init__.py`, `tests/unosat/test_common.py`
- Modify: `pyproject.toml` (etl group)

**Interfaces:**
- Produces: `CONTAINER = "global"`, `BRONZE = "unosat/bronze"`, `META = f"{BRONZE}/_meta"`, `USER_AGENT`, `LEDGER_COLS: list[str]`, `TERMINAL_STATUSES`, `RETRYABLE_STATUSES`, `HARVEST_FORMATS`;
  `parse_event_code(name: str) -> dict | None` returning `{"event_code", "hazard_prefix", "iso3"}`;
  `scope_for(prefix: str | None) -> str` (`flood` for FL/TC, `unknown` for None, else `other`);
  `blob_path(sha256: str, basename: str) -> str`;
  `coerce_ledger_dtypes(df) -> df`; `global_settings(stage) -> Settings`;
  `make_session() -> requests.Session`; `class HostLimiter` with `acquire(url) -> contextmanager`.

- [ ] **Step 1: Create the branch and add dependencies**

```bash
cd /Users/zackarno/Documents/CHD/repos/ds-geospatial-impact-estimates
git checkout -b feat/unosat-archive docs/unosat-archive-spec
```

Edit `pyproject.toml`, `[dependency-groups]` → `etl`, so it reads:

```toml
etl = [
    "ocha-lens",
    "ocha-stratus>=0.1.7",
    # UNOSAT archive (pipelines/unosat): HDX catalogue client + cache-dir convention
    "hdx-python-api>=6.3",
    "platformdirs>=4.0",
]
```

Run: `uv lock && uv sync --group etl --group api`
Expected: lock updates, `uv run --group etl python -c "import hdx.api, platformdirs; print('ok')"` prints `ok`.

- [ ] **Step 2: Write the failing tests**

`tests/unosat/__init__.py`: empty file.

`tests/unosat/test_common.py`:

```python
import threading
import time

from gie.unosat import common


def test_parse_event_code_from_resource_name():
    assert common.parse_event_code("FL20220424SSD_SHP.zip") == {
        "event_code": "FL20220424SSD",
        "hazard_prefix": "FL",
        "iso3": "SSD",
    }
    assert common.parse_event_code("TC20220221MDG_gdb.zip")["hazard_prefix"] == "TC"


def test_parse_event_code_rejects_non_matching_names():
    assert common.parse_event_code("UNOSAT_PopulationExposure_20260826_Nepal.xlsx") is None
    assert common.parse_event_code("") is None


def test_scope_for_prefix():
    assert common.scope_for("FL") == "flood"
    assert common.scope_for("TC") == "flood"
    assert common.scope_for("EQ") == "other"
    assert common.scope_for(None) == "unknown"


def test_blob_path_is_content_addressed():
    sha = "a" * 64
    assert common.blob_path(sha, "FL20220424SSD_SHP.zip") == (
        "unosat/bronze/blob=" + sha + "/FL20220424SSD_SHP.zip"
    )


def test_status_vocabularies_are_disjoint_and_complete():
    all_statuses = {
        "pending", "excluded_kmz", "uploaded", "uploaded_dedup",
        "failed_download", "failed_upload", "unavailable_404", "corrupt_upstream",
    }
    assert common.TERMINAL_STATUSES <= all_statuses
    assert common.RETRYABLE_STATUSES <= all_statuses
    assert not (common.TERMINAL_STATUSES & common.RETRYABLE_STATUSES)
    assert common.TERMINAL_STATUSES == {"unavailable_404", "corrupt_upstream"}
    assert common.RETRYABLE_STATUSES == {"failed_download", "failed_upload"}


def test_host_limiter_caps_concurrency_per_host():
    lim = common.HostLimiter(max_per_host=2)
    active = {"n": 0, "peak": 0}
    lock = threading.Lock()

    def work():
        with lim.acquire("https://unosat.org/x.zip"):
            with lock:
                active["n"] += 1
                active["peak"] = max(active["peak"], active["n"])
            time.sleep(0.05)
            with lock:
                active["n"] -= 1

    threads = [threading.Thread(target=work) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert active["peak"] == 2


def test_host_limiter_is_per_host():
    lim = common.HostLimiter(max_per_host=1)
    with lim.acquire("https://unosat.org/a.zip"):
        # a different host is not blocked by the first host's slot
        with lim.acquire("https://unosat-maps.web.cern.ch/b.zip"):
            pass


def test_session_has_user_agent_and_retries():
    s = common.make_session()
    assert s.headers["User-Agent"].startswith("OCHA-CHD-DS unosat-archive")
    adapter = s.get_adapter("https://unosat.org/")
    assert adapter.max_retries.total == 4
    assert 429 in adapter.max_retries.status_forcelist
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unosat/test_common.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'gie.unosat'`

- [ ] **Step 4: Write the implementation**

`src/gie/unosat/__init__.py`: empty.

`src/gie/unosat/common.py`:

```python
"""Shared plumbing for the UNOSAT archive (pipelines/unosat).

The archive lands in container ``global`` under ``unosat/`` because it is a
general historical corpus, not event-scoped project data (same reasoning as
the CEMS flood archive, ADR-0029). Bronze is content-addressed: one object
per distinct sha256, because HDX datasets are cumulative snapshots that
re-ship the same zip many times (spec §Decisions).
"""

from __future__ import annotations

import dataclasses
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from gie.config import Settings, load_settings

CONTAINER = "global"
BRONZE = "unosat/bronze"
META = f"{BRONZE}/_meta"
USER_AGENT = "OCHA-CHD-DS unosat-archive (ds-geospatial-impact-estimates)"
PROVIDER = "United Nations Satellite Centre (UNOSAT), via HDX"

# Resource formats we archive. KMZ are map graphics: inventoried, not fetched.
HARVEST_FORMATS = ("SHP", "Geodatabase", "XLSX", "Geopackage")

# Upstream said no, permanently (stable across retries hours apart): never retried.
TERMINAL_STATUSES = frozenset({"unavailable_404", "corrupt_upstream"})
# Our side or transient upstream: retried only with --retry-failed.
RETRYABLE_STATUSES = frozenset({"failed_download", "failed_upload"})
UPLOADED_STATUSES = frozenset({"uploaded", "uploaded_dedup"})

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
```

- [ ] **Step 5: Run tests and lint**

Run: `uv run pytest tests/unosat/test_common.py -q && uv run ruff check src/gie/unosat tests/unosat`
Expected: 8 passed, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/gie/unosat tests/unosat
git commit -m "unosat: package scaffold — constants, event-code parsing, status vocabulary, polite session"
```

---

### Task 2: Local content-addressed cache

**Files:**
- Create: `src/gie/unosat/cache.py`, `tests/unosat/test_cache.py`

**Interfaces:**
- Consumes: `common.BRONZE`, `common.blob_path`.
- Produces: `cache_root() -> Path`; `cache_path(sha256: str, basename: str) -> Path`;
  `read_through(sha256: str, basename: str, fetch: Callable[[], bytes], *, enabled: bool = True) -> Path` (returns the local path, fetching once if absent).

- [ ] **Step 1: Write the failing tests**

`tests/unosat/test_cache.py`:

```python
from pathlib import Path

import pytest

from gie.unosat import cache


def test_cache_root_prefers_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("GIE_CACHE_DIR", str(tmp_path / "custom"))
    assert cache.cache_root() == tmp_path / "custom"


def test_cache_root_defaults_to_platformdirs(monkeypatch):
    monkeypatch.delenv("GIE_CACHE_DIR", raising=False)
    root = cache.cache_root()
    assert root.name == "gie"


def test_cache_path_mirrors_bronze_layout(monkeypatch, tmp_path):
    monkeypatch.setenv("GIE_CACHE_DIR", str(tmp_path))
    sha = "b" * 64
    assert cache.cache_path(sha, "X.zip") == tmp_path / "unosat" / "bronze" / f"blob={sha}" / "X.zip"


def test_read_through_fetches_once_then_hits(monkeypatch, tmp_path):
    monkeypatch.setenv("GIE_CACHE_DIR", str(tmp_path))
    calls = {"n": 0}

    def fetch() -> bytes:
        calls["n"] += 1
        return b"zipbytes"

    p1 = cache.read_through("c" * 64, "A.zip", fetch)
    p2 = cache.read_through("c" * 64, "A.zip", fetch)
    assert p1 == p2 and p1.read_bytes() == b"zipbytes"
    assert calls["n"] == 1


def test_read_through_disabled_uses_temp_and_still_returns_bytes(monkeypatch, tmp_path):
    monkeypatch.setenv("GIE_CACHE_DIR", str(tmp_path))
    p = cache.read_through("d" * 64, "A.zip", lambda: b"x", enabled=False)
    assert p.read_bytes() == b"x"
    assert not (tmp_path / "unosat").exists()  # nothing persisted under the cache


def test_read_through_writes_atomically(monkeypatch, tmp_path):
    monkeypatch.setenv("GIE_CACHE_DIR", str(tmp_path))

    def bad_fetch() -> bytes:
        raise OSError("network")

    with pytest.raises(OSError):
        cache.read_through("e" * 64, "A.zip", bad_fetch)
    target = cache.cache_path("e" * 64, "A.zip")
    assert not target.exists()
    assert not list(Path(target.parent).glob("*.part")) if target.parent.exists() else True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unosat/test_cache.py -q`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError`.

- [ ] **Step 3: Write the implementation**

`src/gie/unosat/cache.py`:

```python
"""Local mirror of the content-addressed bronze layout (spec §2b).

Because paths are keyed by sha256 the cache is never stale: a file exists at
its hash path or it does not. Harvest writes through; silver reads through.
Blob is the source of truth; this directory is disposable.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from platformdirs import user_cache_dir

from gie.unosat import common


def cache_root() -> Path:
    env = os.getenv("GIE_CACHE_DIR")
    return Path(env) if env else Path(user_cache_dir("gie"))


def cache_path(sha256: str, basename: str) -> Path:
    return cache_root() / common.blob_path(sha256, basename)


def read_through(
    sha256: str, basename: str, fetch: Callable[[], bytes], *, enabled: bool = True
) -> Path:
    """Return a local file holding the content for ``sha256``/``basename``,
    calling ``fetch`` only when it is not already cached. Writes are atomic
    (temp file + rename) so a killed run never leaves a truncated file at
    the final path. With ``enabled=False`` the bytes go to a temp file
    outside the cache (caller owns cleanup)."""
    if not enabled:
        fd, tmp = tempfile.mkstemp(suffix=basename)
        with os.fdopen(fd, "wb") as f:
            f.write(fetch())
        return Path(tmp)
    dest = cache_path(sha256, basename)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    try:
        part.write_bytes(fetch())
        os.replace(part, dest)
    finally:
        if part.exists():
            part.unlink()
    return dest
```

- [ ] **Step 4: Run tests and lint**

Run: `uv run pytest tests/unosat/test_cache.py -q && uv run ruff check src/gie/unosat tests/unosat`
Expected: 6 passed, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/gie/unosat/cache.py tests/unosat/test_cache.py
git commit -m "unosat: local content-addressed cache with atomic read-through"
```

---

### Task 3: Discovery — HDX catalogue to ledger

**Files:**
- Create: `src/gie/unosat/discovery.py`, `pipelines/unosat/discovery.py`, `tests/unosat/test_discovery.py`

**Interfaces:**
- Consumes: `common.LEDGER_COLS`, `common.parse_event_code`, `common.scope_for`, `common.host_of`, `common.HARVEST_FORMATS`, `common.coerce_ledger_dtypes`.
- Produces: `fetch_unosat_datasets(user_agent: str) -> list[dict]` (live HDX; each dict has the dataset fields plus `"resources": list[dict]`);
  `datasets_table(datasets: list[dict]) -> pd.DataFrame`;
  `resources_ledger(datasets: list[dict]) -> pd.DataFrame` (one row per resource version, `LEDGER_COLS`, statuses `pending` / `excluded_kmz`);
  `merge_ledgers(fresh, old) -> pd.DataFrame`.
  Ledger `target_id = f"{resource_id}@{last_modified}"`.

- [ ] **Step 1: Write the failing tests**

`tests/unosat/test_discovery.py`:

```python
import pandas as pd

from gie.unosat import common, discovery

DS = {
    "id": "ds-1",
    "name": "satellite-detected-water-extents-south-sudan",
    "title": "Satellite detected water extents between 14 and 18 December 2024 over South Sudan",
    "dataset_date": "[2024-12-20T00:00:00 TO 2024-12-20T23:59:59]",
    "metadata_created": "2024-12-20T10:00:00.000000",
    "metadata_modified": "2024-12-21T10:00:00.000000",
    "license_id": "cc-by-sa",
    "groups": [{"title": "South Sudan", "name": "ssd"}],
    "tags": [{"name": "flooding"}, {"name": "geodata"}],
    "notes": "text",
    "methodology": "Other",
    "methodology_other": "SAR + VIIRS",
    "resources": [
        {
            "id": "r-shp", "name": "FL20220424SSD_SHP.zip", "format": "SHP",
            "url": "https://unosat.org/static/x/FL20220424SSD_SHP.zip",
            "size": 56726504, "hash": "abc", "last_modified": "2024-12-20T09:00:00",
        },
        {
            "id": "r-gdb", "name": "FL20220424SSD_gdb.zip", "format": "Geodatabase",
            "url": "https://unosat-maps.web.cern.ch/SS/FL20220424SSD_gdb.zip",
            "size": 20680843, "hash": None, "last_modified": "2024-12-20T09:00:00",
        },
        {
            "id": "r-kmz", "name": "FL20220424SSD.kmz", "format": "KMZ",
            "url": "https://unosat.org/static/x/FL20220424SSD.kmz",
            "size": 100, "hash": None, "last_modified": "2024-12-20T09:00:00",
        },
        {
            "id": "r-xlsx", "name": "UNOSAT_PopulationExposure_SouthSudan.xlsx", "format": "XLSX",
            "url": "https://unosat.org/static/x/exposure.xlsx",
            "size": 38572, "hash": "def", "last_modified": "2024-12-20T09:00:00",
        },
    ],
}


def test_datasets_table_flattens_groups_tags_and_licence():
    t = discovery.datasets_table([DS])
    assert len(t) == 1
    row = t.iloc[0]
    assert row["countries"] == "South Sudan"
    assert row["tags"] == "flooding; geodata"
    assert row["licence"] == "cc-by-sa"
    assert row["n_resources"] == 4


def test_resources_ledger_one_row_per_resource_with_statuses():
    led = discovery.resources_ledger([DS])
    assert list(led.columns) == common.LEDGER_COLS
    assert len(led) == 4
    by = led.set_index("resource_id")
    assert by.loc["r-shp", "status"] == "pending"
    assert by.loc["r-gdb", "status"] == "pending"
    assert by.loc["r-xlsx", "status"] == "pending"
    assert by.loc["r-kmz", "status"] == "excluded_kmz"


def test_resources_ledger_parses_event_code_scope_and_host():
    by = discovery.resources_ledger([DS]).set_index("resource_id")
    assert by.loc["r-shp", "event_code"] == "FL20220424SSD"
    assert by.loc["r-shp", "hazard_prefix"] == "FL"
    assert by.loc["r-shp", "iso3"] == "SSD"
    assert by.loc["r-shp", "scope"] == "flood"
    assert by.loc["r-gdb", "host"] == "unosat-maps.web.cern.ch"
    assert pd.isna(by.loc["r-xlsx", "event_code"])
    assert by.loc["r-xlsx", "scope"] == "unknown"


def test_target_id_is_resource_version():
    by = discovery.resources_ledger([DS]).set_index("resource_id")
    assert by.loc["r-shp", "target_id"] == "r-shp@2024-12-20T09:00:00"


def test_merge_keeps_transfer_outcomes_and_flags_vanished():
    fresh = discovery.resources_ledger([DS])
    old = fresh.copy()
    old.loc[old.resource_id == "r-shp", ["status", "sha256", "size_bytes", "attempts"]] = [
        "uploaded", "f" * 64, 56726504, 1,
    ]
    gone = old.iloc[[0]].copy()
    gone["target_id"] = "r-old@2020-01-01T00:00:00"
    gone["resource_id"] = "r-old"
    gone["status"] = "uploaded"
    old = pd.concat([old, gone], ignore_index=True)

    merged = discovery.merge_ledgers(fresh, old).set_index("target_id")
    assert merged.loc["r-shp@2024-12-20T09:00:00", "status"] == "uploaded"
    assert merged.loc["r-shp@2024-12-20T09:00:00", "sha256"] == "f" * 64
    assert merged.loc["r-old@2020-01-01T00:00:00", "missing_upstream"]
    assert not merged.loc["r-gdb@2024-12-20T09:00:00", "missing_upstream"]


def test_merge_treats_new_version_as_new_row():
    fresh = discovery.resources_ledger([DS])
    old = fresh.copy()
    old["status"] = "uploaded"
    # upstream re-published r-shp with a new last_modified -> new target_id
    bumped = dict(DS)
    bumped["resources"] = [dict(DS["resources"][0], last_modified="2025-01-01T00:00:00")]
    fresh2 = discovery.resources_ledger([bumped])
    merged = discovery.merge_ledgers(fresh2, old)
    assert (merged.status == "pending").sum() == 1
    assert merged.loc[merged.status == "pending", "target_id"].item() == "r-shp@2025-01-01T00:00:00"
    assert merged.loc[merged.target_id == "r-shp@2024-12-20T09:00:00", "missing_upstream"].item()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unosat/test_discovery.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the library implementation**

`src/gie/unosat/discovery.py`:

```python
"""Build the harvest ledger from the HDX catalogue (spec §1).

One ledger row per RESOURCE VERSION (``{resource_id}@{last_modified}``): a
resource re-published upstream becomes a new row; the old row is kept and
flagged ``missing_upstream`` when it no longer appears. Re-running is the
backfill mechanism: fresh discovery merges onto the existing ledger and
transfer outcomes survive (same model as cems_flood/discovery.py).
"""

from __future__ import annotations

import pandas as pd

from gie.unosat import common

_TRANSFER_COLS = [
    "status", "http_status", "error", "attempts", "attempted_at",
    "uploaded_at", "sha256", "size_bytes", "n_members",
]
_TRANSFER_STATUSES = common.UPLOADED_STATUSES | common.RETRYABLE_STATUSES | common.TERMINAL_STATUSES


def fetch_unosat_datasets(user_agent: str = common.USER_AGENT) -> list[dict]:
    """Every dataset of HDX organisation ``unosat`` with its resources, as plain
    dicts. Live call; not unit-tested (the pure functions below are)."""
    from hdx.api.configuration import Configuration
    from hdx.data.dataset import Dataset

    try:
        Configuration.create(hdx_site="prod", user_agent=user_agent, hdx_read_only=True)
    except Exception as e:  # already configured in this process
        if "already" not in str(e).lower():
            raise
    datasets = Dataset.search_in_hdx(fq="organization:unosat", page_size=1000)
    out: list[dict] = []
    for ds in datasets:
        d = dict(ds)
        d["resources"] = [dict(r) for r in ds.get_resources()]
        out.append(d)
    if not out:
        raise RuntimeError("HDX returned zero UNOSAT datasets — catalogue or auth problem")
    return out


def datasets_table(datasets: list[dict]) -> pd.DataFrame:
    rows = []
    for d in datasets:
        rows.append(
            {
                "dataset_id": d["id"],
                "dataset_name": d["name"],
                "title": d.get("title"),
                "dataset_date": d.get("dataset_date"),
                "countries": "; ".join(g.get("title") or g.get("name") for g in d.get("groups") or []),
                "tags": "; ".join(t["name"] for t in d.get("tags") or []),
                "licence": d.get("license_id"),
                "notes": d.get("notes"),
                "methodology": d.get("methodology_other") or d.get("methodology"),
                "metadata_created": d.get("metadata_created"),
                "metadata_modified": d.get("metadata_modified"),
                "n_resources": len(d.get("resources") or []),
            }
        )
    return pd.DataFrame(rows)


def resources_ledger(datasets: list[dict]) -> pd.DataFrame:
    rows = []
    for d in datasets:
        for r in d.get("resources") or []:
            code = common.parse_event_code(r.get("name") or "") or {}
            fmt = r.get("format")
            rows.append(
                {
                    "target_id": f"{r['id']}@{r.get('last_modified')}",
                    "dataset_id": d["id"],
                    "dataset_name": d["name"],
                    "resource_id": r["id"],
                    "resource_name": r.get("name"),
                    "format": fmt,
                    "url": r.get("url"),
                    "host": common.host_of(r.get("url") or ""),
                    "hdx_size": r.get("size"),
                    "hdx_hash": r.get("hash") or None,
                    "last_modified": r.get("last_modified"),
                    "event_code": code.get("event_code"),
                    "hazard_prefix": code.get("hazard_prefix"),
                    "iso3": code.get("iso3"),
                    "scope": common.scope_for(code.get("hazard_prefix")),
                    "licence": d.get("license_id"),
                    "status": "pending" if fmt in common.HARVEST_FORMATS else "excluded_kmz",
                    "attempts": 0,
                    "missing_upstream": False,
                }
            )
    led = pd.DataFrame(rows).reindex(columns=common.LEDGER_COLS)
    dup = led[led["target_id"].duplicated(keep=False)]
    if len(dup):
        raise RuntimeError(f"duplicate target_id in HDX listing (same resource twice?):\n{dup}")
    return common.coerce_ledger_dtypes(led)


def merge_ledgers(fresh: pd.DataFrame, old: pd.DataFrame) -> pd.DataFrame:
    """Fresh discovery wins on availability; the old ledger wins on transfer
    outcomes; vanished target versions are kept and flagged."""
    old = old.set_index("target_id")
    fresh = fresh.set_index("target_id")
    keep = old[old["status"].isin(_TRANSFER_STATUSES)]
    common_ids = fresh.index.intersection(keep.index)
    fresh.loc[common_ids, _TRANSFER_COLS] = keep.loc[common_ids, _TRANSFER_COLS]
    gone = old.loc[old.index.difference(fresh.index)].copy()
    gone["missing_upstream"] = True
    merged = pd.concat([fresh, gone]).reset_index()
    return common.coerce_ledger_dtypes(merged.reindex(columns=common.LEDGER_COLS))
```

- [ ] **Step 4: Write the CLI**

`pipelines/unosat/discovery.py`:

```python
"""Build/refresh the UNOSAT harvest ledger from HDX.

Writes {work_dir}/datasets.parquet and {work_dir}/resources.parquet (THE
LEDGER). Re-running merges onto the existing ledger: transfer outcomes are
preserved, new or re-published resources become pending, vanished ones are
flagged missing_upstream, never dropped.

Run:  uv run --group etl --group api python pipelines/unosat/discovery.py [--work-dir ...]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from gie.unosat import discovery


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", default="/tmp/gie_unosat_archive", type=Path)
    args = ap.parse_args(argv)
    args.work_dir.mkdir(parents=True, exist_ok=True)

    print("fetching UNOSAT datasets from HDX ...")
    datasets = discovery.fetch_unosat_datasets()
    ds_table = discovery.datasets_table(datasets)
    ledger = discovery.resources_ledger(datasets)
    print(f"datasets: {len(ds_table)}  resources: {len(ledger)}")

    ledger_path = args.work_dir / "resources.parquet"
    if ledger_path.exists():
        old = pd.read_parquet(ledger_path)
        ledger = discovery.merge_ledgers(ledger, old)
        print(f"merged onto existing ledger ({len(old)} rows)")
    ds_table.to_parquet(args.work_dir / "datasets.parquet")
    ledger.to_parquet(ledger_path)

    print(f"\nledger: {len(ledger)} rows -> {ledger_path}")
    print(ledger["status"].value_counts().to_string())
    print("\npending by scope / format:")
    print(ledger[ledger.status == "pending"].groupby(["scope", "format"]).size().to_string())
    print("\nhosts:", ledger.host.value_counts().to_dict())


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests and lint**

Run: `uv run pytest tests/unosat/test_discovery.py -q && uv run ruff check src/gie/unosat pipelines/unosat tests/unosat`
Expected: 6 passed, ruff clean.

- [ ] **Step 6: Run discovery for real**

Run: `uv run --group etl --group api python pipelines/unosat/discovery.py`
Expected: ~1,465 datasets, ~2,984 resources; statuses `pending` ≈ 2,969 and `excluded_kmz` ≈ 15; hosts list shows `unosat.org`, `unosat-maps.web.cern.ch`, `cern.ch`, `data.humdata.org`, `floods.unosat.org`. If counts differ wildly from the spec's evidence table, stop and investigate before harvesting.

- [ ] **Step 7: Commit**

```bash
git add src/gie/unosat/discovery.py pipelines/unosat/discovery.py tests/unosat/test_discovery.py
git commit -m "unosat: discovery — HDX catalogue to resource-version ledger with backfill merge"
```

---

### Task 4: Blob store abstraction and the per-target harvest worker

**Files:**
- Create: `src/gie/unosat/store.py`, `src/gie/unosat/harvest.py`, `tests/unosat/conftest.py`, `tests/unosat/test_harvest.py`

**Interfaces:**
- Consumes: `common.*`, `cache.cache_path`, `gie.blobio.upload`.
- Produces: `class BlobStore(Protocol)` with `exists_size(path) -> int | None`, `upload(path, data: bytes) -> None`, `list_sizes(prefix) -> dict[str, int]`;
  `MemoryStore` (tests) and `DataLakeStore(fs, container_client)` (real);
  `stream_download(session, url, dest: Path, limiter) -> DownloadResult(status_code: int, sha256: str | None, size: int)`;
  `inspect_zip(path: Path) -> list[zipfile.ZipInfo]` (raises `zipfile.BadZipFile`);
  `process_target(row: pd.Series, *, session, store, limiter, use_cache: bool) -> tuple[dict, list[dict]]` (ledger updates, member rows).

- [ ] **Step 1: Write the fixtures and failing tests**

`tests/unosat/conftest.py`:

```python
import io
import zipfile

import pandas as pd
import pytest

from gie.unosat import common


def make_zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def good_zip() -> bytes:
    return make_zip({"FL20220424SSD_SHP/VIIRS_20241214_20241218_FloodExtent_SouthSudan.shp": b"shp",
                     "FL20220424SSD_SHP/VIIRS_20241214_20241218_FloodExtent_SouthSudan.dbf": b"dbf"})


@pytest.fixture
def ledger_row() -> pd.Series:
    row = {c: None for c in common.LEDGER_COLS}
    row.update(
        target_id="r-shp@2024-12-20T09:00:00", resource_id="r-shp",
        resource_name="FL20220424SSD_SHP.zip", format="SHP",
        url="https://unosat.org/static/x/FL20220424SSD_SHP.zip", host="unosat.org",
        event_code="FL20220424SSD", hazard_prefix="FL", iso3="SSD", scope="flood",
        licence="cc-by-sa", status="pending", attempts=0, missing_upstream=False,
    )
    return pd.Series(row)


class FakeResponse:
    def __init__(self, status: int, body: bytes = b""):
        self.status_code = status
        self._body = body
        self.headers = {"Content-Length": str(len(body))}

    def iter_content(self, chunk_size: int):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeSession:
    """Maps url -> FakeResponse or an Exception instance to raise."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url, *, stream=True, timeout=None):
        self.calls.append(url)
        r = self.routes[url]
        if isinstance(r, Exception):
            raise r
        return r
```

`tests/unosat/test_harvest.py`:

```python
import hashlib
import zipfile

import pytest
import requests

from gie.unosat import cache, common, harvest, store
from tests.unosat.conftest import FakeResponse, FakeSession, make_zip


@pytest.fixture(autouse=True)
def _cache_in_tmp(monkeypatch, tmp_path):
    monkeypatch.setenv("GIE_CACHE_DIR", str(tmp_path / "cache"))


def _run(row, resp_or_exc, st=None, use_cache=True):
    session = FakeSession({row["url"]: resp_or_exc})
    st = st or store.MemoryStore()
    updates, members = harvest.process_target(
        row, session=session, store=st, limiter=common.HostLimiter(), use_cache=use_cache
    )
    return updates, members, st


def test_happy_path_uploads_hashes_inventories_and_caches(ledger_row, good_zip):
    updates, members, st = _run(ledger_row, FakeResponse(200, good_zip))
    sha = hashlib.sha256(good_zip).hexdigest()
    assert updates["status"] == "uploaded"
    assert updates["sha256"] == sha
    assert updates["size_bytes"] == len(good_zip)
    assert updates["n_members"] == 2 and len(members) == 2
    assert members[0]["sha256"] == sha and members[0]["target_id"] == ledger_row["target_id"]
    path = common.blob_path(sha, "FL20220424SSD_SHP.zip")
    assert st.exists_size(path) == len(good_zip)
    assert cache.cache_path(sha, "FL20220424SSD_SHP.zip").read_bytes() == good_zip
    assert updates["attempts"] == 1 and updates["http_status"] == 200


def test_dedup_when_blob_already_holds_content(ledger_row, good_zip):
    sha = hashlib.sha256(good_zip).hexdigest()
    st = store.MemoryStore()
    st.upload(common.blob_path(sha, "FL20220424SSD_SHP.zip"), good_zip)
    updates, members, st = _run(ledger_row, FakeResponse(200, good_zip), st)
    assert updates["status"] == "uploaded_dedup"
    assert updates["sha256"] == sha
    assert len(st.uploads) == 1  # no second upload happened
    assert len(members) == 2  # inventory is still recorded for this target


def test_404_is_terminal_unavailable(ledger_row):
    updates, members, _ = _run(ledger_row, FakeResponse(404))
    assert updates["status"] == "unavailable_404"
    assert updates["http_status"] == 404
    assert members == [] and updates.get("sha256") is None


def test_200_but_not_a_zip_is_terminal_corrupt(ledger_row):
    updates, _, st = _run(ledger_row, FakeResponse(200, b"<html>not a zip</html>"))
    assert updates["status"] == "corrupt_upstream"
    assert updates["http_status"] == 200
    assert "BadZipFile" in updates["error"]
    assert st.uploads == {}


def test_network_error_is_retryable_failed_download(ledger_row):
    updates, _, _ = _run(ledger_row, requests.ConnectionError("boom"))
    assert updates["status"] == "failed_download"
    assert "ConnectionError" in updates["error"]


def test_upload_error_is_retryable_failed_upload(ledger_row, good_zip):
    st = store.MemoryStore(fail_upload=True)
    updates, _, _ = _run(ledger_row, FakeResponse(200, good_zip), st)
    assert updates["status"] == "failed_upload"
    assert updates["sha256"] == hashlib.sha256(good_zip).hexdigest()  # hash kept for the retry


def test_no_cache_leaves_nothing_under_cache_root(ledger_row, good_zip, tmp_path):
    _run(ledger_row, FakeResponse(200, good_zip), use_cache=False)
    assert not (tmp_path / "cache" / "unosat").exists()


def test_inspect_zip_raises_on_corrupt_member(tmp_path):
    data = bytearray(make_zip({"a.txt": b"hello world" * 100}))
    data[-40:-30] = b"\x00" * 10  # damage the central directory region
    p = tmp_path / "bad.zip"
    p.write_bytes(bytes(data))
    with pytest.raises(zipfile.BadZipFile):
        harvest.inspect_zip(p)


def test_stream_download_hashes_while_streaming(tmp_path, good_zip):
    session = FakeSession({"https://unosat.org/a.zip": FakeResponse(200, good_zip)})
    res = harvest.stream_download(
        session, "https://unosat.org/a.zip", tmp_path / "a.zip", common.HostLimiter()
    )
    assert res.status_code == 200
    assert res.sha256 == hashlib.sha256(good_zip).hexdigest()
    assert res.size == len(good_zip) == (tmp_path / "a.zip").stat().st_size
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unosat/test_harvest.py -q`
Expected: FAIL with `ModuleNotFoundError` for `gie.unosat.store` / `gie.unosat.harvest`.

- [ ] **Step 3: Write the store abstraction**

`src/gie/unosat/store.py`:

```python
"""Blob store boundary so the harvest worker is testable without Azure.

``DataLakeStore`` is the real thing: uploads via gie.blobio (chunked DFS path,
the documented fix for single-PUT timeouts on this lake) and existence/size
checks via the same filesystem client. ``MemoryStore`` is for tests.
"""

from __future__ import annotations

from typing import Protocol

from gie import blobio


class BlobStore(Protocol):
    def exists_size(self, path: str) -> int | None: ...
    def upload(self, path: str, data: bytes) -> None: ...
    def list_sizes(self, prefix: str) -> dict[str, int]: ...


class MemoryStore:
    def __init__(self, *, fail_upload: bool = False) -> None:
        self.uploads: dict[str, bytes] = {}
        self._fail = fail_upload

    def exists_size(self, path: str) -> int | None:
        return len(self.uploads[path]) if path in self.uploads else None

    def upload(self, path: str, data: bytes) -> None:
        if self._fail:
            raise OSError("simulated upload failure")
        self.uploads[path] = data

    def list_sizes(self, prefix: str) -> dict[str, int]:
        return {p: len(d) for p, d in self.uploads.items() if p.startswith(prefix)}


class DataLakeStore:
    """``fs``: filesystem client from gie.blobio.uploader(settings).
    ``container_client``: ocha_stratus.get_container_client(...) for listing."""

    def __init__(self, fs, container_client) -> None:
        self._fs = fs
        self._cc = container_client

    def exists_size(self, path: str) -> int | None:
        fc = self._fs.get_file_client(path)
        if not fc.exists():
            return None
        return fc.get_file_properties().size

    def upload(self, path: str, data: bytes) -> None:
        blobio.upload(self._fs, data, path)
        got = self._fs.get_file_client(path).get_file_properties().size
        if got != len(data):
            raise OSError(f"size mismatch after upload: blob={got} local={len(data)}")

    def list_sizes(self, prefix: str) -> dict[str, int]:
        return {b.name: b.size for b in self._cc.list_blobs(name_starts_with=prefix)}
```

- [ ] **Step 4: Write the harvest worker**

`src/gie/unosat/harvest.py` (worker half; orchestration helpers are added in Task 5):

```python
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
    updates: dict = {"attempts": int(row["attempts"] or 0) + 1, "attempted_at": _now()}
    basename = row["resource_name"]
    tmpdir = Path(tempfile.mkdtemp(prefix="unosat_"))
    tmp = tmpdir / basename
    try:
        try:
            dl = stream_download(session, row["url"], tmp, limiter)
        except requests.RequestException as e:
            return updates | {"status": "failed_download", "error": f"{type(e).__name__}: {e}"[:300]}, []
        if dl.status_code == 404:
            return updates | {"status": "unavailable_404", "http_status": 404, "error": "HTTP 404"}, []
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
```

- [ ] **Step 5: Run tests and lint**

Run: `uv run pytest tests/unosat/test_harvest.py -q && uv run ruff check src/gie/unosat tests/unosat`
Expected: 9 passed, ruff clean. If `test_inspect_zip_raises_on_corrupt_member` does not raise, corrupt a different byte range (the central directory sits in the last ~100 bytes of a small zip); the assertion is that damaged bytes surface as `BadZipFile`, not silence.

- [ ] **Step 6: Commit**

```bash
git add src/gie/unosat/store.py src/gie/unosat/harvest.py tests/unosat/conftest.py tests/unosat/test_harvest.py
git commit -m "unosat: harvest worker — streaming hash, zip test, content-addressed upload with dedup, explicit upstream states"
```

---

### Task 5: Harvest orchestration — reconcile, journal, checkpoint, CLI

**Files:**
- Modify: `src/gie/unosat/harvest.py` (append orchestration helpers)
- Create: `pipelines/unosat/harvest.py`
- Modify: `tests/unosat/test_harvest.py` (append tests)

**Interfaces:**
- Consumes: `store.BlobStore.list_sizes`, `gie.blobio.upload`, `common.META`.
- Produces: `reconcile_with_blob(ledger, store) -> ledger`; `journal(work: Path, record: dict)`; `transfer_record(row, stage, outcome, **extra) -> dict`; `checkpoint(work, ledger, members, store) -> list[dict]`; constants `META_FILES = ("datasets.parquet", "resources.parquet", "zip_contents.parquet")`, `CHECKPOINT_EVERY = 25`.

- [ ] **Step 1: Write the failing tests** (append to `tests/unosat/test_harvest.py`)

```python
import json

import pandas as pd

from gie.unosat import discovery
from tests.unosat.test_discovery import DS


def _ledger():
    return discovery.resources_ledger([DS]).set_index("target_id", drop=False)


def test_reconcile_marks_rows_whose_content_is_in_blob(good_zip):
    led = _ledger()
    sha = hashlib.sha256(good_zip).hexdigest()
    tid = "r-shp@2024-12-20T09:00:00"
    led.loc[tid, ["status", "sha256", "size_bytes"]] = ["failed_upload", sha, len(good_zip)]
    st = store.MemoryStore()
    st.upload(common.blob_path(sha, "FL20220424SSD_SHP.zip"), good_zip)
    led = harvest.reconcile_with_blob(led, st)
    assert led.loc[tid, "status"] == "uploaded"


def test_reconcile_demotes_uploaded_rows_whose_blob_is_missing(good_zip):
    led = _ledger()
    tid = "r-shp@2024-12-20T09:00:00"
    led.loc[tid, ["status", "sha256", "size_bytes"]] = ["uploaded", "9" * 64, len(good_zip)]
    led = harvest.reconcile_with_blob(led, store.MemoryStore())
    assert led.loc[tid, "status"] == "pending"


def test_reconcile_demotes_size_mismatch(good_zip):
    led = _ledger()
    sha = hashlib.sha256(good_zip).hexdigest()
    tid = "r-shp@2024-12-20T09:00:00"
    led.loc[tid, ["status", "sha256", "size_bytes"]] = ["uploaded", sha, len(good_zip)]
    st = store.MemoryStore()
    st.upload(common.blob_path(sha, "FL20220424SSD_SHP.zip"), good_zip[:-5])  # truncated copy
    led = harvest.reconcile_with_blob(led, st)
    assert led.loc[tid, "status"] == "pending"


def test_reconcile_leaves_terminal_and_pending_rows_alone():
    led = _ledger()
    led.loc["r-gdb@2024-12-20T09:00:00", "status"] = "unavailable_404"
    led = harvest.reconcile_with_blob(led, store.MemoryStore())
    assert led.loc["r-gdb@2024-12-20T09:00:00", "status"] == "unavailable_404"
    assert led.loc["r-shp@2024-12-20T09:00:00", "status"] == "pending"


def test_journal_and_transfer_record_shape(tmp_path, ledger_row):
    rec = harvest.transfer_record(ledger_row, "dev", "uploaded", sha256="x" * 64, size_bytes=5)
    for key in ("ts", "outcome", "target_id", "source", "dataset", "provider", "licence",
                "origin_url", "host", "blob_path", "stage"):
        assert key in rec
    assert rec["source"] == "unosat" and rec["licence"] == "cc-by-sa"
    assert rec["blob_path"] == common.blob_path("x" * 64, "FL20220424SSD_SHP.zip")
    harvest.journal(tmp_path, rec)
    lines = (tmp_path / "transfers.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["outcome"] == "uploaded"


def test_checkpoint_writes_ledger_members_and_uploads_meta(tmp_path):
    led = _ledger()
    st = store.MemoryStore()
    (tmp_path / "datasets.parquet").write_bytes(b"")  # exists -> should be uploaded
    members = [{"target_id": "t", "sha256": "s", "event_code": "E", "member": "a.shp",
                "file_size": 1, "compress_size": 1}]
    left = harvest.checkpoint(tmp_path, led, members, st)
    assert left == []
    assert (tmp_path / "resources.parquet").exists()
    assert len(pd.read_parquet(tmp_path / "zip_contents.parquet")) == 1
    assert f"{common.META}/resources.parquet" in st.uploads
    assert f"{common.META}/zip_contents.parquet" in st.uploads
    # second checkpoint merges member rows per target_id instead of duplicating
    harvest.checkpoint(tmp_path, led, members, st)
    assert len(pd.read_parquet(tmp_path / "zip_contents.parquet")) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unosat/test_harvest.py -q`
Expected: the 6 new tests FAIL with `AttributeError: module ... has no attribute 'reconcile_with_blob'` etc.

- [ ] **Step 3: Append orchestration helpers to `src/gie/unosat/harvest.py`**

```python
import json  # noqa: E402  (add to the import block at the top of the module)

META_FILES = ("datasets.parquet", "resources.parquet", "zip_contents.parquet")
CHECKPOINT_EVERY = 25


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

    to_mark = size_ok & ~status.isin(common.UPLOADED_STATUSES) & ~status.isin(common.TERMINAL_STATUSES)
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


def checkpoint(work: Path, ledger: pd.DataFrame, members: list[dict], store: BlobStore) -> list[dict]:
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
```

Note for `DataLakeStore.upload`: it verifies size after upload, which is right for zips and harmless for the small metadata files.

- [ ] **Step 4: Write the CLI** `pipelines/unosat/harvest.py`

```python
"""Transfer every pending ledger row into content-addressed bronze:
download -> testzip -> inventory -> upload (unless content already there) -> record.

Resume model: the blob store is truth. Every run reconciles the ledger against
a listing of bronze; already-uploaded content is skipped; ledger rows claiming
uploaded whose object is gone are demoted (loudly). Ledger + journal
checkpoint locally AND to blob every 25 items and on exit (incl. Ctrl-C).
Terminal upstream states (unavailable_404, corrupt_upstream) are never
retried; --retry-failed re-attempts failed_download / failed_upload.

Run:  uv run --group etl --group api python pipelines/unosat/harvest.py
      [--limit N] [--stage dev] [--retry-failed] [--dry-run] [--workers 6] [--no-cache]
      [--scope flood|other|unknown ...]
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import ocha_stratus as stratus
import pandas as pd

from gie import blobio
from gie.unosat import common, harvest
from gie.unosat.store import DataLakeStore


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", default="/tmp/gie_unosat_archive", type=Path)
    ap.add_argument("--stage", default="dev", choices=["dev", "prod"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--per-host", type=int, default=3)
    ap.add_argument("--sleep", type=float, default=0.1, help="per-worker pre-download stagger")
    ap.add_argument("--no-cache", action="store_true", help="do not keep downloads in the local cache")
    ap.add_argument("--scope", nargs="*", default=None, help="restrict to ledger scopes")
    args = ap.parse_args(argv)

    ledger_path = args.work_dir / "resources.parquet"
    if not ledger_path.exists():
        raise FileNotFoundError(f"{ledger_path} missing - run discovery.py first")
    ledger = pd.read_parquet(ledger_path).set_index("target_id", drop=False)
    ledger.index.name = None
    ledger = common.coerce_ledger_dtypes(ledger)

    cc = stratus.get_container_client(container_name=common.CONTAINER, stage=args.stage)
    fs = blobio.uploader(common.global_settings(args.stage))
    store = DataLakeStore(fs, cc)

    ledger = harvest.reconcile_with_blob(ledger, store)
    wanted = ["pending"] + (sorted(common.RETRYABLE_STATUSES) if args.retry_failed else [])
    todo = ledger[ledger["status"].isin(wanted)]
    if args.scope:
        todo = todo[todo["scope"].isin(args.scope)]
    todo = todo.sort_values(["scope", "target_id"])
    if args.limit:
        todo = todo.head(args.limit)
    print(f"targets to transfer: {len(todo)} ({ledger['status'].value_counts().to_dict()})")
    if args.dry_run:
        print(todo[["target_id", "resource_name", "format", "host", "status"]].head(30).to_string())
        return

    limiter = common.HostLimiter(args.per_host)
    import threading

    local = threading.local()

    def session():
        if not hasattr(local, "s"):
            local.s = common.make_session()
        return local.s

    def worker(row: pd.Series):
        time.sleep(args.sleep)
        updates, members = harvest.process_target(
            row, session=session(), store=store, limiter=limiter, use_cache=not args.no_cache
        )
        return row["target_id"], updates, members

    members_buf: list[dict] = []
    done = 0
    pool = ThreadPoolExecutor(max_workers=args.workers)
    try:
        futures = [pool.submit(worker, row) for _, row in todo.iterrows()]
        for fut in as_completed(futures):
            target_id, updates, members = fut.result()  # bugs propagate here
            for col, val in updates.items():
                ledger.loc[target_id, col] = val
            members_buf.extend(members)
            outcome = updates["status"]
            harvest.journal(
                args.work_dir,
                harvest.transfer_record(
                    ledger.loc[target_id], args.stage, outcome,
                    size_bytes=updates.get("size_bytes"), sha256=updates.get("sha256"),
                    error=updates.get("error"),
                ),
            )
            done += 1
            marker = "ok" if outcome in common.UPLOADED_STATUSES else f"** {outcome}: {updates.get('error')}"
            print(f"  [{done}/{len(todo)}] {target_id} {outcome if outcome in common.UPLOADED_STATUSES else marker}", flush=True)
            if done % harvest.CHECKPOINT_EVERY == 0:
                members_buf = harvest.checkpoint(args.work_dir, ledger, members_buf, store)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        harvest.checkpoint(args.work_dir, ledger, members_buf, store)

    counts = ledger["status"].value_counts()
    print(f"\nfinal ledger:\n{counts.to_string()}")
    failed = ledger[ledger["status"].isin(common.RETRYABLE_STATUSES)]
    if len(failed):
        print(f"\nFAILURES ({len(failed)}) - rerun with --retry-failed:")
        print(failed[["target_id", "status", "http_status", "error"]].to_string())
    terminal = ledger[ledger["status"].isin(common.TERMINAL_STATUSES)]
    if len(terminal):
        print(f"\nUPSTREAM UNAVAILABLE ({len(terminal)}) - recorded, not retried:")
        print(terminal[["target_id", "status", "error"]].to_string())


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests and lint**

Run: `uv run pytest tests/unosat -q && uv run ruff check src/gie/unosat pipelines/unosat tests/unosat`
Expected: all pass (29 tests so far), ruff clean. If ruff flags the in-function `import threading`, move it to the module imports.

- [ ] **Step 6: Smoke test against dev blob with a tiny limit**

Run: `uv run --group etl --group api python pipelines/unosat/harvest.py --dry-run` then
`uv run --group etl --group api python pipelines/unosat/harvest.py --limit 5 --scope flood`
Expected: five lines ending `uploaded` (or `uploaded_dedup` on a re-run), `resources.parquet` and `transfers.jsonl` present in the work dir and under `global/unosat/bronze/_meta/`, and the objects under `unosat/bronze/blob=<sha>/`. Run the same command again: all five come back `uploaded_dedup` or are skipped by reconcile (status already uploaded). Verify with:

```bash
uv run --group etl python -c "
import ocha_stratus as s; print(sorted(s.list_container_blobs(name_starts_with='unosat/bronze/', stage='dev', container_name='global'))[:12])"
```

- [ ] **Step 7: Commit**

```bash
git add src/gie/unosat/harvest.py pipelines/unosat/harvest.py tests/unosat/test_harvest.py
git commit -m "unosat: harvest orchestration — reconcile against blob census, journal, checkpoints, resumable CLI"
```

---

### Task 6: Coded-value domains from every geodatabase

**Files:**
- Create: `src/gie/unosat/domains.py`, `pipelines/unosat/domains.py`, `tests/unosat/test_domains.py`

**Interfaces:**
- Consumes: `cache.read_through`, `common.BRONZE`, ledger `resources.parquet` (rows with `format == "Geodatabase"` and status in `UPLOADED_STATUSES`).
- Produces: `ogrinfo_json(gdb_path: Path) -> dict` (runs `ogrinfo -json -ro`; raises `RuntimeError` if the binary is missing or exits non-zero);
  `domain_rows(sha256: str, info: dict) -> list[dict]` with keys `sha256, layer, field, domain_name, code, value`;
  `domains_for_gdb_zip(sha256: str, zip_path: Path) -> tuple[list[dict], str]` returning rows and a status `ok | no_domains | no_gdb_in_zip`;
  outputs `_meta/domains.parquet` and `_meta/domains_status.parquet` (`sha256, status, n_rows, processed_at`).

- [ ] **Step 1: Write the failing tests**

`tests/unosat/test_domains.py`:

```python
import zipfile

import pytest

from gie.unosat import domains

INFO = {
    "layers": [
        {
            "name": "VIIRS_20211119_20211123_FloodExtent_SouthSudan",
            "fields": [
                {"name": "Water_Class", "domainName": "Water_Class2"},
                {"name": "Sensor_ID", "domainName": "SensorID_v2"},
                {"name": "Notes"},
            ],
        },
        {
            "name": "KS_20140505_Flood",
            "fields": [{"name": "Water_Class", "domainName": "Water_Class"}],
        },
        {"name": "Water_Class", "fields": [{"name": "Water_Class_code"}, {"name": "Water_Class_txt"}]},
    ],
    "domains": {
        "Water_Class": {"type": "coded", "codedValues": {"0": "Preflood Water", "1": "Flood Water"}},
        "Water_Class2": {"type": "coded", "codedValues": {"0": "Archive Water Extent / Pre-Flood Water",
                                                         "2": "Satellite Detected Water / Possible Saturated Soil"}},
        "SensorID_v2": {"type": "coded", "codedValues": {"53": "VIIRS-NOAA"}},
        "Boolean": {"type": "coded", "codedValues": {"0": "No", "1": "Yes"}},
    },
}


def test_domain_rows_are_bound_per_layer_and_field():
    rows = domains.domain_rows("s" * 64, INFO)
    keyed = {(r["layer"], r["field"], r["code"]): r["value"] for r in rows}
    assert keyed[("VIIRS_20211119_20211123_FloodExtent_SouthSudan", "Water_Class", "0")] == (
        "Archive Water Extent / Pre-Flood Water"
    )
    assert keyed[("KS_20140505_Flood", "Water_Class", "0")] == "Preflood Water"
    assert keyed[("VIIRS_20211119_20211123_FloodExtent_SouthSudan", "Sensor_ID", "53")] == "VIIRS-NOAA"
    assert all(r["sha256"] == "s" * 64 for r in rows)
    # unbound fields and unused domains produce no rows
    assert not any(r["field"] == "Notes" for r in rows)
    assert not any(r["domain_name"] == "Boolean" for r in rows)


def test_domain_rows_empty_when_no_domains():
    assert domains.domain_rows("s" * 64, {"layers": [{"name": "L", "fields": [{"name": "a"}]}]}) == []


def test_domains_for_gdb_zip_without_gdb(tmp_path):
    p = tmp_path / "x.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("a.shp", b"x")
    rows, status = domains.domains_for_gdb_zip("s" * 64, p)
    assert rows == [] and status == "no_gdb_in_zip"


def test_ogrinfo_missing_binary_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))  # no ogrinfo here
    with pytest.raises(RuntimeError, match="ogrinfo"):
        domains.ogrinfo_json(tmp_path / "nothing.gdb")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unosat/test_domains.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

`src/gie/unosat/domains.py`:

```python
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


def ogrinfo_json(gdb_path: Path) -> dict:
    exe = shutil.which("ogrinfo")
    if exe is None:
        raise RuntimeError("ogrinfo not found on PATH — install GDAL (brew install gdal)")
    proc = subprocess.run([exe, "-json", "-ro", str(gdb_path)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ogrinfo failed on {gdb_path}: {proc.stderr.strip()[:500]}")
    return json.loads(proc.stdout)


def domain_rows(sha256: str, info: dict) -> list[dict]:
    doms = info.get("domains") or {}
    rows: list[dict] = []
    for layer in info.get("layers") or []:
        for field in layer.get("fields") or []:
            dname = field.get("domainName")
            if not dname or dname not in doms:
                continue
            coded = doms[dname].get("codedValues") or {}
            items = coded.items() if isinstance(coded, dict) else ((c["code"], c["value"]) for c in coded)
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


def domains_for_gdb_zip(sha256: str, zip_path: Path) -> tuple[list[dict], str]:
    """Extract the zip to a temp dir, run ogrinfo on each .gdb inside, collect rows."""
    with zipfile.ZipFile(zip_path) as z:
        gdb_dirs = sorted({n.split(".gdb/")[0] + ".gdb" for n in z.namelist() if ".gdb/" in n})
        if not gdb_dirs:
            return [], "no_gdb_in_zip"
        tmp = Path(tempfile.mkdtemp(prefix="unosat_gdb_"))
        try:
            z.extractall(tmp)
            rows: list[dict] = []
            for g in gdb_dirs:
                rows.extend(domain_rows(sha256, ogrinfo_json(tmp / g)))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return rows, ("ok" if rows else "no_domains")


def status_row(sha256: str, status: str, n_rows: int) -> dict:
    return {
        "sha256": sha256,
        "status": status,
        "n_rows": n_rows,
        "processed_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
```

`pipelines/unosat/domains.py`:

```python
"""Extract coded-value domains from every uploaded geodatabase in bronze.

Reads each distinct GDB content once (through the local cache; fetched from
blob if absent), writes {work_dir}/domains.parquet and domains_status.parquet
and uploads both to unosat/bronze/_meta/. Resumable: sha256 values already in
domains_status are skipped.

Run:  uv run --group etl --group api python pipelines/unosat/domains.py [--stage dev] [--limit N]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import ocha_stratus as stratus
import pandas as pd

from gie import blobio
from gie.unosat import cache, common, domains


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", default="/tmp/gie_unosat_archive", type=Path)
    ap.add_argument("--stage", default="dev", choices=["dev", "prod"])
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)

    led = pd.read_parquet(args.work_dir / "resources.parquet")
    gdbs = led[(led["format"] == "Geodatabase") & led["status"].isin(common.UPLOADED_STATUSES)]
    gdbs = gdbs.drop_duplicates("sha256")
    status_path = args.work_dir / "domains_status.parquet"
    rows_path = args.work_dir / "domains.parquet"
    done = pd.read_parquet(status_path) if status_path.exists() else pd.DataFrame(columns=["sha256"])
    todo = gdbs[~gdbs["sha256"].isin(done["sha256"])]
    if args.limit:
        todo = todo.head(args.limit)
    print(f"distinct GDBs: {len(gdbs)}, to process: {len(todo)}")

    cc = stratus.get_container_client(container_name=common.CONTAINER, stage=args.stage)
    fs = blobio.uploader(common.global_settings(args.stage))
    all_rows: list[dict] = []
    statuses: list[dict] = []
    for i, r in enumerate(todo.itertuples(), 1):
        path = cache.read_through(
            r.sha256, r.resource_name,
            lambda r=r: cc.download_blob(common.blob_path(r.sha256, r.resource_name)).readall(),
        )
        rows, status = domains.domains_for_gdb_zip(r.sha256, path)
        all_rows.extend(rows)
        statuses.append(domains.status_row(r.sha256, status, len(rows)))
        print(f"  [{i}/{len(todo)}] {r.resource_name} {status} ({len(rows)} rows)", flush=True)

    if statuses:
        new_status = pd.concat([done, pd.DataFrame(statuses)], ignore_index=True)
        new_status.to_parquet(status_path)
        old_rows = pd.read_parquet(rows_path) if rows_path.exists() else pd.DataFrame()
        pd.concat([old_rows, pd.DataFrame(all_rows)], ignore_index=True).to_parquet(rows_path)
        for name in ("domains.parquet", "domains_status.parquet"):
            blobio.upload(fs, (args.work_dir / name).read_bytes(), f"{common.META}/{name}")
    print(pd.read_parquet(status_path)["status"].value_counts().to_string() if status_path.exists() else "nothing processed")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests and lint**

Run: `uv run pytest tests/unosat/test_domains.py -q && uv run ruff check src/gie/unosat pipelines/unosat tests/unosat`
Expected: 4 passed, ruff clean.

- [ ] **Step 5: Smoke test on the GDBs harvested in Task 5**

Run: `uv run --group etl --group api python pipelines/unosat/domains.py --limit 3`
Expected: each GDB prints `ok (N rows)` or `no_domains`; `domains.parquet` shows `Water_Class` / `Water_Class2` / `SensorID_v2` bound per layer.

- [ ] **Step 6: Commit**

```bash
git add src/gie/unosat/domains.py pipelines/unosat/domains.py tests/unosat/test_domains.py
git commit -m "unosat: coded-value domains per (gdb, layer, field) via ogrinfo, resumable"
```

---

### Task 7: Bronze audit (B1–B3)

**Files:**
- Create: `src/gie/unosat/audit.py`, `pipelines/unosat/audit.py`, `tests/unosat/test_audit.py`

**Interfaces:**
- Consumes: ledger DataFrame, `store.BlobStore.list_sizes`, `domains_status.parquet`.
- Produces: `check_b1_no_pending(ledger) -> tuple[bool, str]`; `check_b2_census(ledger, store) -> tuple[bool, str]`; `check_b3_domains(ledger, status_df) -> tuple[bool, str]`; `run_bronze_checks(ledger, store, status_df) -> bool`.

- [ ] **Step 1: Write the failing tests**

`tests/unosat/test_audit.py`:

```python
import hashlib

import pandas as pd

from gie.unosat import audit, common, discovery, store
from tests.unosat.test_discovery import DS


def _uploaded_ledger(data: bytes):
    led = discovery.resources_ledger([DS])
    sha = hashlib.sha256(data).hexdigest()
    led.loc[led.status == "pending", ["status", "sha256", "size_bytes"]] = ["uploaded", sha, len(data)]
    return led, sha


def test_b1_fails_on_pending():
    led = discovery.resources_ledger([DS])
    ok, detail = audit.check_b1_no_pending(led)
    assert not ok and "3" in detail  # three pending rows in the fixture


def test_b2_passes_when_census_matches(good_zip):
    led, sha = _uploaded_ledger(good_zip)
    st = store.MemoryStore()
    for name in led.loc[led.status == "uploaded", "resource_name"]:
        st.upload(common.blob_path(sha, name), good_zip)
    ok, _ = audit.check_b2_census(led, st)
    assert ok


def test_b2_fails_on_missing_or_extra_or_wrong_size(good_zip):
    led, sha = _uploaded_ledger(good_zip)
    st = store.MemoryStore()
    names = list(led.loc[led.status == "uploaded", "resource_name"])
    st.upload(common.blob_path(sha, names[0]), good_zip[:-1])  # wrong size
    st.upload(common.blob_path("0" * 64, "stray.zip"), b"x")  # not in ledger
    ok, detail = audit.check_b2_census(led, st)
    assert not ok
    assert "missing" in detail and "extra" in detail and "size" in detail


def test_b3_requires_domain_status_for_every_uploaded_gdb(good_zip):
    led, sha = _uploaded_ledger(good_zip)
    ok, detail = audit.check_b3_domains(led, pd.DataFrame(columns=["sha256", "status"]))
    assert not ok and sha[:8] in detail
    ok, _ = audit.check_b3_domains(led, pd.DataFrame({"sha256": [sha], "status": ["no_domains"]}))
    assert ok
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unosat/test_audit.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

`src/gie/unosat/audit.py`:

```python
"""Bronze invariants (spec §5, B-rules). Each check returns (ok, detail)."""

from __future__ import annotations

import pandas as pd

from gie.unosat import common
from gie.unosat.store import BlobStore


def check_b1_no_pending(ledger: pd.DataFrame) -> tuple[bool, str]:
    n = int((ledger["status"] == "pending").sum())
    return n == 0, f"{n} pending"


def check_b2_census(ledger: pd.DataFrame, store: BlobStore) -> tuple[bool, str]:
    """Every uploaded row's (sha256, basename) exists with the recorded size,
    and every object under bronze/blob= is claimed by some uploaded row."""
    up = ledger[ledger["status"].isin(common.UPLOADED_STATUSES)]
    expected = {
        common.blob_path(r.sha256, r.resource_name): int(r.size_bytes) for r in up.itertuples()
    }
    got = store.list_sizes(f"{common.BRONZE}/blob=")
    missing = sorted(set(expected) - set(got))
    extra = sorted(set(got) - set(expected))
    wrong = sorted(p for p in set(expected) & set(got) if expected[p] != got[p])
    ok = not (missing or extra or wrong)
    detail = f"{len(got)} objects; missing={len(missing)} extra={len(extra)} size-mismatch={len(wrong)}"
    if not ok:
        detail += f" | missing[:3]={missing[:3]} extra[:3]={extra[:3]} size[:3]={wrong[:3]}"
    return ok, detail


def check_b3_domains(ledger: pd.DataFrame, status_df: pd.DataFrame) -> tuple[bool, str]:
    gdb = ledger[(ledger["format"] == "Geodatabase") & ledger["status"].isin(common.UPLOADED_STATUSES)]
    want = set(gdb["sha256"].dropna())
    have = set(status_df["sha256"]) if len(status_df) else set()
    missing = sorted(want - have)
    return not missing, f"{len(want)} GDBs; without domain status: {len(missing)} {missing[:3]}"


def run_bronze_checks(ledger: pd.DataFrame, store: BlobStore, status_df: pd.DataFrame) -> bool:
    ok = True
    for name, (passed, detail) in {
        "B1 no pending targets": check_b1_no_pending(ledger),
        "B2 blob census matches ledger (paths+sizes, both directions)": check_b2_census(ledger, store),
        "B3 every uploaded GDB has a domains status": check_b3_domains(ledger, status_df),
    }.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}  {detail}")
        ok &= passed
    return ok
```

`pipelines/unosat/audit.py`:

```python
"""Invariant checks for the UNOSAT bronze archive. Exit 1 on any failure.

Run:  uv run --group etl --group api python pipelines/unosat/audit.py [--stage dev]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import ocha_stratus as stratus
import pandas as pd

from gie import blobio
from gie.unosat import audit, common
from gie.unosat.store import DataLakeStore


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", default="/tmp/gie_unosat_archive", type=Path)
    ap.add_argument("--stage", default="dev", choices=["dev", "prod"])
    args = ap.parse_args(argv)

    ledger = common.coerce_ledger_dtypes(pd.read_parquet(args.work_dir / "resources.parquet"))
    status_path = args.work_dir / "domains_status.parquet"
    status_df = pd.read_parquet(status_path) if status_path.exists() else pd.DataFrame(columns=["sha256", "status"])
    cc = stratus.get_container_client(container_name=common.CONTAINER, stage=args.stage)
    store = DataLakeStore(blobio.uploader(common.global_settings(args.stage)), cc)

    print("bronze:")
    ok = audit.run_bronze_checks(ledger, store, status_df)
    print("\nledger statuses:", ledger["status"].value_counts().to_dict())
    if not ok:
        sys.exit(1)
    print("ALL BRONZE CHECKS PASSED")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests and lint**

Run: `uv run pytest tests/unosat -q && uv run ruff check src/gie/unosat pipelines/unosat tests/unosat`
Expected: all pass (37 tests), ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/gie/unosat/audit.py pipelines/unosat/audit.py tests/unosat/test_audit.py
git commit -m "unosat: bronze audit — pending, two-way blob census with sizes, domain coverage"
```

---

### Task 8: Run the full harvest, README, ADR, data ledger

**Files:**
- Create: `pipelines/unosat/README.md`, `docs/decisions/0033-unosat-flood-archive-content-addressed-bronze.md`
- Modify: `data_ledger.md` (append one row after the harvest completes)

- [ ] **Step 1: Run the harvest to completion (unattended, resumable)**

```bash
uv run --group etl --group api python pipelines/unosat/harvest.py --scope flood 2>&1 | tee /tmp/gie_unosat_archive/harvest_flood.log
uv run --group etl --group api python pipelines/unosat/harvest.py 2>&1 | tee /tmp/gie_unosat_archive/harvest_all.log
uv run --group etl --group api python pipelines/unosat/harvest.py --retry-failed
```

Expected order of magnitude: ~2,970 targets, ~22 GB of distinct content uploaded, a few hundred `uploaded_dedup`, ~6 `corrupt_upstream`, ~19 `unavailable_404`, zero `failed_*` after the retry pass. Anything left in `failed_*` after two retry passes is investigated (host? size? timeout?) and either fixed in code or documented in the README, never deleted from the ledger.

- [ ] **Step 2: Extract domains and audit**

```bash
uv run --group etl --group api python pipelines/unosat/domains.py
uv run --group etl --group api python pipelines/unosat/audit.py
```

Expected: `ALL BRONZE CHECKS PASSED`. If B2 fails, re-run harvest (reconcile fixes ledger drift) and audit again; if it still fails, the detail names the paths.

- [ ] **Step 3: Write the README** `pipelines/unosat/README.md`

```markdown
# UNOSAT archive harvester (bronze)

Archives every UNOSAT product resource catalogued on HDX (all hazards) into a
content-addressed bronze layer on blob, with a ledger that accounts for every
resource version: fetched, deduplicated, or explicitly unavailable upstream.
Design: `docs/superpowers/specs/2026-09-18-unosat-flood-archive-design.md`;
decision record: ADR-0033.

HDX is the catalogue, not the store: bytes come from unosat.org and CERN hosts.

```
global/unosat/bronze/blob={sha256}/{basename}     one object per distinct content
global/unosat/bronze/_meta/datasets.parquet        HDX dataset metadata
global/unosat/bronze/_meta/resources.parquet       THE LEDGER (one row per resource version)
global/unosat/bronze/_meta/zip_contents.parquet    member inventory per target
global/unosat/bronze/_meta/domains.parquet         (sha256, layer, field, domain, code, value)
global/unosat/bronze/_meta/domains_status.parquet  per-GDB: ok | no_domains | no_gdb_in_zip
global/unosat/bronze/_meta/transfers.jsonl         append-only journal
```

## Run

```sh
uv run --group etl --group api python pipelines/unosat/discovery.py           # build/refresh ledger
uv run --group etl --group api python pipelines/unosat/harvest.py --dry-run   # preview
uv run --group etl --group api python pipelines/unosat/harvest.py             # transfer (resumable)
uv run --group etl --group api python pipelines/unosat/harvest.py --retry-failed
uv run --group etl --group api python pipelines/unosat/domains.py             # GDB domains
uv run --group etl --group api python pipelines/unosat/audit.py               # invariants
```

Needs `.env` with `DSCI_AZ_BLOB_DEV_SAS_WRITE` (via `gie.config`) and GDAL's
`ogrinfo` on PATH (`brew install gdal`). Default stage dev.

## Statuses

| status | meaning | retried? |
|---|---|---|
| pending | has URL, will be fetched | — |
| excluded_kmz | map graphic, inventoried only | never |
| uploaded | transferred and size-verified | — |
| uploaded_dedup | identical content already in bronze; ledger points at it | — |
| failed_download / failed_upload | our side or transient upstream | `--retry-failed` |
| unavailable_404 | upstream says gone (stable across hours) | never |
| corrupt_upstream | HTTP 200 but not a zip | never |

## Local cache

Downloads are kept at `$GIE_CACHE_DIR` (default `platformdirs.user_cache_dir("gie")`)
mirroring the bronze layout, so silver reads them without re-downloading.
Content-addressed, therefore never stale; delete freely. `--no-cache` disables.

## Guarantees

Blob is truth: every run reconciles the ledger against a bronze listing.
Checkpoints every 25 transfers and on exit. Every attempt is journaled.
Re-running discovery is the backfill: new/re-published resources become
pending, vanished ones are flagged `missing_upstream`, never dropped.
```

- [ ] **Step 4: Write ADR-0033** `docs/decisions/0033-unosat-flood-archive-content-addressed-bronze.md` (copy the template frontmatter)

```markdown
---
status: "accepted"
date: 2026-09-18
deciders: Zack Arno
---

# UNOSAT archive: content-addressed bronze from the HDX catalogue, SHP and GDB both archived, GDB authoritative

## Context and Problem Statement

The flood-fusion work needs analyst-made flood and water extents outside
Europe. UNOSAT publishes ~1,465 datasets on HDX, but HDX is only the
catalogue: bytes sit on five UNOSAT/CERN hosts, datasets are cumulative
snapshots that re-ship the same zip dozens of times (515 of 1,516 zips are
content-identical to another), and older layers store coded attributes whose
meaning lives only in the geodatabase's domain tables. How do we archive this
so nothing is lost, nothing is duplicated, and the codes stay decodable?

## Decision Drivers

* Upstream loses data (19 stable 404s, 6 HTML-as-zip) and has no SLA.
* Duplication is structural, not incidental.
* 2014–2021 attributes are integer codes bound to per-layer domains.
* One reader in `ds-flood-gfm` must serve CEMS and UNOSAT labels alike.

## Considered Options

* Bronze keyed by HDX dataset/resource (mirrors the catalogue; stores each
  identical zip up to 41 times).
* Bronze keyed by event code (like CEMS `code=`; UNOSAT resource names are
  not always parseable and one zip carries several attribute event codes).
* **Bronze keyed by sha256, ledger rows pointing at content (CHOSEN).**
* Archive SHP only (smaller; loses domains and 55 GDB-only feature classes in
  one event) vs SHP + GDB (CHOSEN).

## Decision Outcome

Content-addressed bronze (`blob={sha256}/{basename}`) with a resource-version
ledger; both SHP and GDB archived; silver reads the GDB first because it is
a superset with typed, domain-bound attributes and is authoritative where
exports disagree. Discovery uses `hdx-python-api` read-only. Terminal
upstream states are ledger statuses, never retries.

### Consequences

* Good: identical content stored once; the ledger, not the blob path, carries
  HDX identity; domains survive; resume and audit are exact.
* Bad: a blob path says nothing human-readable about its content (the ledger
  is required to navigate); two formats of the same product are kept.
```

- [ ] **Step 5: Append the data ledger row** to `data_ledger.md`, matching its table columns (source, layer, description, path, notes, status, date), with the real counts from the audit output:

```markdown
| unosat | bronze | UNOSAT product zips from HDX, all hazards, content-addressed | global/unosat/bronze/ (blob={sha256}/, _meta/) | N distinct objects, M ledger rows; K unavailable upstream recorded; domains for J GDBs | ingested | 2026-09-XX |
```

- [ ] **Step 6: Lint, full tests, commit**

```bash
uv run pytest tests -q && uv run ruff check src pipelines/unosat tests
git add pipelines/unosat/README.md docs/decisions/0033-unosat-flood-archive-content-addressed-bronze.md data_ledger.md
git commit -m "unosat: bronze archive complete — README, ADR-0033, data ledger row"
```

- [ ] **Step 7: Open the PR**

Branch `feat/unosat-archive` → `v1`. PR body: link the spec and ADR, paste the final audit output and ledger status counts. (Merge the spec branch `docs/unosat-archive-spec` first or include it; the feature branch already contains it.)

---

## Self-review against the spec

- §Decisions: sibling in this repo ✔ (Tasks 1–8 under `pipelines/unosat` + `src/gie/unosat`); all hazards to bronze ✔ (Task 3 statuses, Task 8 run); HDX catalogue vs hosts ✔ (`host` column, journal, README); content-addressed ✔ (Task 4); SHP and GDB ✔ (`HARVEST_FORMATS`); water/flood separation and gold v2 — silver/gold, **next plan**; `hdx-python-api` ✔ (Task 3).
- §1 Discovery: every ledger column ✔; `target_id` version semantics ✔; merge ✔; `hdx_hash` recorded ✔ (its use for skipping downloads stays an open question).
- §2 Harvest: stream+hash ✔, testzip ✔, inventory ✔, dedup ✔, journal ✔, reconcile ✔, checkpoints ✔, terminal vs retryable ✔, six workers + per-host cap ✔, licence per dataset ✔. Domains per (layer, field) ✔ (Task 6).
- §2b Cache: read-through ✔, write-through ✔, `--no-cache` ✔, platformdirs ✔.
- §5 B1–B3 ✔ (Task 7). S/G rules → next plan.
- §Testing: tests live in `tests/unosat/` (repo `testpaths`), not `pipelines/unosat/tests/` as the spec says — deliberate, so pytest collects them; note this when the spec is next touched.
- Placeholders: none. Type consistency: `process_target` signature, `BlobStore` methods, `common.blob_path`, and status strings are identical across Tasks 4–7.
