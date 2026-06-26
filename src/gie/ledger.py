"""A tiny Markdown ingestion ledger.

A human-readable record of what has been landed in the blob lake, maintained by
the pipeline loaders. Idempotency itself lives in the blob layout (see
docs/decisions/0005); this is the at-a-glance provenance view. Deliberately a
flat Markdown table so it is readable in the repo and trivially portable to a
Postgres ledger once the team adopts shared Postgres.

Upserts are keyed by (source, layer, dataset); re-recording identical content is
a no-op (no date churn, no file rewrite).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

LEDGER_PATH = Path(__file__).resolve().parents[2] / "data_ledger.md"
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
