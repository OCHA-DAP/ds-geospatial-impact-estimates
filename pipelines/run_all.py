"""Run the whole VENEZUELA pipeline in dependency order — one command to refresh
everything after new coverage or data arrives.

Every step is idempotent (skip-if-present / overwrite), so re-running only does
the work that's actually new: new CEMS products are polled, the Overture base
auto-extends to any admin-1 state newly touched by coverage, and the gold is
rebuilt. Safe to run repeatedly.

Event-parametrized steps (ADR-0027) receive the VE event explicitly via argv;
the remaining steps are VE-pinned modules. The Colombia chain runs the same
scripts with --event 20260810-co-earthquake (plus harmonize_microsoft_hdx /
harmonize_common_co in place of the VE-only adapters).

Run: uv run --group etl python pipelines/run_all.py
"""

from __future__ import annotations

import importlib
import time

EVENT = "20260624-ve-earthquake"

# (module, argv or None, one-line description) in dependency order
STEPS = [
    ("ingest_cems", ["--event", EVENT], "poll Copernicus EMS for newly delivered products"),
    ("harmonize_cems", ["--event", EVENT], "CEMS damage silver + native gold"),
    ("cems_coverage", ["--event", EVENT], "CEMS analysed extent (AOI minus cloud) + detail"),
    ("ingest_footprints", None, "Microsoft footprints + valid-area masks"),
    ("ingest_overture", ["--event", EVENT], "Overture base for coverage-touched adm1 states"),
    ("aggregate_damage", ["--event", EVENT], "Microsoft native gold"),
    ("harmonize_common", None, "common-model gold — all sources on one base, coverage-aware"),
    ("stage_serving", ["--event", EVENT], "stage serving geometries to tiered gold (ADR-0016)"),
]


def main() -> None:
    t0 = time.time()
    for i, (mod, argv, desc) in enumerate(STEPS, 1):
        print(f"\n{'=' * 72}\n[{i}/{len(STEPS)}] {mod} — {desc}\n{'=' * 72}", flush=True)
        m = importlib.import_module(f"pipelines.{mod}")
        m.main(argv) if argv is not None else m.main()
    print(f"\nDone — full refresh in {time.time() - t0:.0f}s.", flush=True)


if __name__ == "__main__":
    main()
