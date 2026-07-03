"""Run the whole pipeline in dependency order — one command to refresh
everything after new coverage or data arrives.

Every step is idempotent (skip-if-present / overwrite), so re-running only does
the work that's actually new: new CEMS products are polled, the Overture base
auto-extends to any admin-1 state newly touched by coverage, and the gold is
rebuilt. Safe to run repeatedly.

Run: uv run --group etl python pipelines/run_all.py
"""

from __future__ import annotations

import importlib
import time

# (module, one-line description) in dependency order
STEPS = [
    ("ingest_cems", "poll Copernicus EMS for newly delivered products"),
    ("harmonize_cems", "CEMS damage silver + native gold"),
    ("cems_coverage", "CEMS analysed extent (imagery in AOI, minus cloud) + detail"),
    ("ingest_footprints", "Microsoft footprints + valid-area masks"),
    ("ingest_overture", "Overture base for every admin-1 state coverage touches"),
    ("aggregate_damage", "Microsoft native gold"),
    ("harmonize_common", "common-model gold — all sources on one base, coverage-aware"),
    ("stage_serving", "stage server-rendered serving geometries into tiered gold (ADR-0016)"),
]


def main() -> None:
    t0 = time.time()
    for i, (mod, desc) in enumerate(STEPS, 1):
        print(f"\n{'=' * 72}\n[{i}/{len(STEPS)}] {mod} — {desc}\n{'=' * 72}", flush=True)
        importlib.import_module(f"pipelines.{mod}").main()
    print(f"\nDone — full refresh in {time.time() - t0:.0f}s.", flush=True)


if __name__ == "__main__":
    main()
