"""Reconstruct the release/availability timeline for the VEN earthquake damage products.

Clock-zero is the USGS mainshock origin time. For each product we record the best
locally-available anchor for *our operational availability* — the git commit that
first landed the loader / ingested the product — plus any product-internal date
(SAR acquisition, activation). Provider *release* dates are an open item to confirm;
our-ingest is an upper bound on them.

Outputs (into this folder):
  - timeline_events.csv : one row per milestone, with latency vs the mainshock.

Evidence sources & confidence:
  - EVENT (mainshock origin) : USGS ComCat us6000t7zp  -> HIGH (authoritative).
  - our_ingest_utc          : git author date of the first-ingest commit -> HIGH,
                              but it marks *integration*, so it is an UPPER BOUND on
                              when the file actually reached us, and on provider release.
  - internal_date           : product metadata (S1 acquisition, product datestamp) -> HIGH.
  - provider_release        : NOT captured here -> TO CONFIRM with providers / HDX.

Run: uv run --group etl python exploratory/paper/timeline/build_timeline.py
(No blob/credentials needed — pure git + constants.)
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

# --- Clock zero: USGS mainshock us6000t7zp (M7.5, 28 km SE of Yumare) -----------
# Origin epoch 1782338711566 ms -> 2026-06-24T22:05:11.566Z. Foreshock us6000t7zc
# (M7.2) struck 38 s earlier; treated as the same event for latency purposes.
EVENT = datetime(2026, 6, 24, 22, 5, 11, tzinfo=timezone.utc)

# --- Milestones -----------------------------------------------------------------
# ingest_iso = git author date (%aI) of the first commit that ingested/integrated
# the product; carries its own UTC offset, converted to UTC below.
# internal_date = ISO of product-internal anchor (acquisition/datestamp), or "".
# channel: how it reached us. release_conf: our-ingest is an upper bound on release.
ROWS = [
    # source, product/milestone, ingest_commit, ingest_iso, internal_date, channel, note
    ("overture", "Exposure base (release 2026-06-17.0) — PRE-EVENT, not a damage product",
     "5ed390b", "2026-06-26T15:04:00-06:00", "2026-06-17", "provider",
     "Baseline building stock; excluded from latency ranking."),
    ("copernicus_ems", "CEMS EMSR884 — first delivered damage products",
     "4c9ee7c", "2026-06-26T14:10:33-06:00", "", "CEMS portal",
     "REFERENCE STANDARD. Incremental delivery: 10 delivered / 9 pending as of 06-28; "
     "consolidated grading ~07-02. Activation timestamp TO CONFIRM."),
    ("microsoft", "Microsoft — Catia La Mar (first AOI)",
     "e261099", "2026-06-26T11:51:24-06:00", "", "HDX",
     "Optical ML footprint damage. Delivered AOI-by-AOI (see later MS rows)."),
    ("microsoft", "Microsoft — +La Guaira +Caraballeda AOIs",
     "7da3722", "2026-06-27T08:51:18-06:00", "", "HDX", ""),
    ("microsoft", "Microsoft — +2 more AOIs (5 total)",
     "f26462a", "2026-06-28T13:17:29-06:00", "", "HDX", ""),
    ("impact_initiatives", "IMPACT v1 — Sentinel-1 SAR damage-proxy RASTER",
     "a0a9652", "2026-06-28T14:38:29-06:00", "2026-06-25T10:15:31+00:00", "email",
     "First SAR signal. S1 acquisitions 2026-06-25 10:15Z & 22:42Z (~12h/~24h post-event). "
     "Preliminary hotspot screen, later superseded by v2 vector."),
    ("microsoft", "Microsoft — merged/deduplicated (all 5 AOIs)",
     "f969fe6", "2026-06-29T11:41:23-06:00", "", "HDX",
     "72,162 dedup buildings; the analysis-ready MS product."),
    ("osu", "OSU/NASA — Sentinel-1 coherence damage",
     "ee15d2e", "2026-06-29T13:38:23-04:00", "2026-06-25", "provider",
     "S1 coherence change; ships an analyzed-area (coverage) polygon."),
    ("hot_osm", "HOT fAIr — AI+crowd damage points (La Guaira)",
     "a33abe0", "2026-06-29T13:01:33-06:00", "", "HDX",
     "Detected-only: no analysed AOI."),
    ("unep_debris", "UNEP/OCHA JEU — building-debris mass",
     "4935989", "2026-07-01T14:58:24-06:00", "", "HDX",
     "Debris MASS (tonnes), not a damage grade. Detected-only."),
    ("usgs", "USGS ShakeMap — MMI contours (seismic CONTEXT)",
     "f9030ae", "2026-07-01T15:08:08-06:00", "2026-06-24T22:05:11+00:00", "USGS API",
     "Context/exposure covariate, not a damage product."),
    ("impact_initiatives", "IMPACT v2 — Sentinel-1 VECTOR damage (supersedes v1)",
     "0c6f6f6", "2026-07-02T15:04:36-06:00", "2026-06-25", "email",
     "81,437 damaged Overture footprints + true swath AOI. The corrected IMPACT product."),
    ("disha", "DISHA (UNOPS) — ML damage inference, NW Caracas",
     "35c295b", "2026-07-02T15:04:51-06:00", "", "provider (restricted)",
     "LICENCE-GATED: no public redistribution/derivative without UNOPS authorization."),
]


def _utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(timezone.utc)


def main() -> None:
    out = Path(__file__).with_name("timeline_events.csv")
    rows_sorted = sorted(ROWS, key=lambda r: _utc(r[3]))
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "source", "milestone", "ingest_commit", "our_ingest_utc",
            "latency_days_from_mainshock", "internal_date", "channel",
            "our_ingest_confidence", "provider_release", "note",
        ])
        for source, milestone, commit, iso, internal, channel, note in rows_sorted:
            ingest = _utc(iso)
            latency = (ingest - EVENT).total_seconds() / 86400.0
            w.writerow([
                source, milestone, commit, ingest.strftime("%Y-%m-%d %H:%MZ"),
                f"{latency:.2f}", internal or "", channel,
                "HIGH (git commit; = integration, upper bound on receipt)",
                "TO CONFIRM (<= our_ingest)", note,
            ])
    print(f"Mainshock (clock zero): {EVENT.isoformat()}")
    print(f"Wrote {out}")
    print()
    print(f"{'latency(d)':>10}  {'our_ingest_utc':<17}  source / milestone")
    for source, milestone, commit, iso, internal, channel, note in rows_sorted:
        latency = (_utc(iso) - EVENT).total_seconds() / 86400.0
        print(f"{latency:>10.2f}  {_utc(iso).strftime('%Y-%m-%d %H:%MZ'):<17}  {source}: {milestone}")


if __name__ == "__main__":
    main()
