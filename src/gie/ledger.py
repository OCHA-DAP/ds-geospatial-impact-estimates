"""A tiny Markdown ingestion ledger + a per-file transfer log.

Two complementary records, both maintained by the pipeline loaders:

* ``data_ledger.md`` (:func:`record`) — the human-readable, dataset-level
  provenance view. Upserts keyed by (source, layer, dataset); re-recording
  identical content is a no-op (no date churn, no file rewrite).
* ``data_transfers.jsonl`` (:func:`log_transfer`) — the machine-readable,
  per-file download/upload log: one append-only JSON line per file landed in
  the lake, capturing origin URL, checksum, size, destination blob path,
  licence and the reference-vs-analysis category. Idempotent: a re-run that
  lands nothing new appends nothing.

Idempotency itself lives in the blob layout (see docs/decisions/0005); these
are the provenance views. Deliberately flat repo files (Markdown / JSONL) so
they are readable + diffable in the repo and trivially portable to a Postgres
ledger once the team adopts shared Postgres.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

LEDGER_PATH = Path(__file__).resolve().parents[2] / "data_ledger.md"
TRANSFERS_PATH = Path(__file__).resolve().parents[2] / "data_transfers.jsonl"

# How a source is used downstream (viewer legend section, evaluation role):
#   reference — human-made ground truth / base data (expert grading, field or
#               crowd mapping: CEMS grading, CODAB, ...)
#   analysis  — automated / ML-derived damage products (Microsoft, SAR proxies, ...)
CATEGORIES = ("reference", "analysis")
_COLS = ["source", "layer", "dataset", "path", "detail", "status", "updated"]
_PREAMBLE = (
    "# Data ingestion ledger\n\n"
    "Auto-maintained by the pipeline loaders — a human-readable record of what is "
    "in the blob lake. Idempotency lives in the blob layout (see "
    "`docs/decisions/0005`); this is the provenance view. Interim Markdown format, "
    "portable to a Postgres ledger later.\n\n"
)


def _key(row: dict[str, str]) -> tuple[str, str, str]:
    return (row["source"], row["layer"], row["dataset"])


def _read() -> dict[tuple[str, str, str], dict[str, str]]:
    rows: dict[tuple[str, str, str], dict[str, str]] = {}
    if not LEDGER_PATH.exists():
        return rows
    for line in LEDGER_PATH.read_text().splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(_COLS) or cells[0] == "source":
            continue
        if set("".join(cells)) <= {"-", ":"}:  # separator row
            continue
        row = dict(zip(_COLS, cells, strict=True))
        rows[_key(row)] = row
    return rows


def _write(rows: dict[tuple[str, str, str], dict[str, str]]) -> None:
    header = "| " + " | ".join(_COLS) + " |"
    sep = "| " + " | ".join(["---"] * len(_COLS)) + " |"
    body = [
        "| " + " | ".join(rows[k][c] for c in _COLS) + " |"
        for k in sorted(rows)
    ]
    LEDGER_PATH.write_text(_PREAMBLE + "\n".join([header, sep, *body]) + "\n")


def record(
    source: str, layer: str, dataset: str, path: str, detail: str, status: str = "ingested"
) -> None:
    """Upsert one ledger entry. No-op if nothing but the date would change."""
    rows = _read()
    entry = {
        "source": source,
        "layer": layer,
        "dataset": dataset,
        "path": path,
        "detail": detail,
        "status": status,
        "updated": date.today().isoformat(),
    }
    old = rows.get(_key(entry))
    unchanged = old and all(old[c] == entry[c] for c in _COLS if c != "updated")
    if unchanged:
        return
    rows[_key(entry)] = entry
    _write(rows)


def sha256_hex(data: bytes) -> str:
    """Checksum helper so loaders don't each import hashlib."""
    return hashlib.sha256(data).hexdigest()


def log_transfer(
    *,
    event: str | None,
    source: str,
    category: str,
    dataset: str,
    origin_url: str,
    blob_path: str,
    size_bytes: int,
    sha256: str,
    stage: str,
    provider: str | None = None,
    licence: str | None = None,
    origin_meta: dict | None = None,
    path: Path = TRANSFERS_PATH,
) -> bool:
    """Append one per-file transfer record to ``data_transfers.jsonl``.

    Call once per file actually landed (downloaded from ``origin_url`` and
    uploaded to ``blob_path``). Returns True if a line was appended, False if
    an identical transfer (same ``sha256`` -> same ``blob_path``) is already
    logged — so idempotent loader re-runs leave the log untouched.

    ``category`` is the downstream role of the source and must be one of
    ``CATEGORIES`` (fail loudly on typos, it drives the viewer legend split).
    ``origin_meta`` carries origin-system identifiers worth keeping (HDX
    resource id / last_modified, CEMS product version, ...).
    """
    if category not in CATEGORIES:
        raise ValueError(f"category {category!r} not in {CATEGORIES}")
    if path.exists():
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            prev = json.loads(line)
            if prev["sha256"] == sha256 and prev["blob_path"] == blob_path:
                return False
    entry = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "event": event,
        "source": source,
        "category": category,
        "dataset": dataset,
        "provider": provider,
        "licence": licence,
        "origin_url": origin_url,
        "origin_meta": origin_meta or {},
        "size_bytes": size_bytes,
        "sha256": sha256,
        "blob_path": blob_path,
        "stage": stage,
    }
    with path.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return True
