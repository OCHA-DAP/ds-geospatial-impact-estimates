"""Stage the server-rendered serving geometries into the tiered gold layer (ADR-0016).

Registry-driven, one event per run: ``--event <event_id>`` (ADR-0027). A few
layers are server-rendered — the FastAPI reads blob and returns GeoJSON — and
read SILVER, which the prod/dev split (ADR-0014) does NOT tier. So a dev harmonize
changes prod for those layers with no promote (that's how the IMPACT v2 AOI outline
leaked to prod ahead of the numbers). This copies those served geometries **verbatim**
(schema preserved) from silver into the event's ``gold/model=common/.../serving/``,
where the loaders now read them — ``az_path("gold")`` resolves to ``gold-prod`` on
the prod slot, so the reads become promote-gated like the rest of the served tier.

Staged (verbatim):
  * per-source ``analysed_extent`` -> serving/extent/source=<src>.parquet
    (sources without an extent for this event are skipped — expected, printed)
  * CEMS ``coverage_detail`` -> serving/coverage_detail.parquet

Run after the harmonizers, before ``promote.py``. See ADR-0016.
Run: uv run --group etl python pipelines/stage_serving.py --event 20260810-co-earthquake
"""

from __future__ import annotations

import argparse

import ocha_stratus as stratus

from gie import blobio, events, ledger
from gie.config import common_segments, load_settings, source_segments

STAGE = "dev"
# Sources whose analysed_extent outline is server-rendered (detected-only
# sources like hot_osm have none; absent sources for an event are skipped).
EXTENT_SOURCES = ["impact_initiatives", "osu", "microsoft", "copernicus_ems", "disha", "list"]


def _copy(fs, settings, src_blob: str, dest_blob: str) -> int:
    data = stratus.load_blob_data(src_blob, stage=STAGE, container_name=settings.container)
    blobio.upload(fs, data, dest_blob)
    return len(data)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--event", required=True, help="event_id from events.yaml whose serving layers to stage"
    )
    args = parser.parse_args(argv)
    ev = events.get_event(args.event)  # fails loudly on an unregistered event
    if len(ev.countries) != 1:
        raise NotImplementedError(
            f"event {ev.event_id} spans countries {ev.countries} — pick the common-tree "
            "layout for multi-country deliberately."
        )
    adm0 = ev.countries[0]
    settings = load_settings(STAGE)
    fs = blobio.uploader(settings)
    eid = ev.event_id

    def _gold(*parts: str) -> str:
        return settings.blob_path(
            "gold", *common_segments(eid, adm0), "serving", *parts, event=eid
        )

    cc = stratus.get_container_client(stage=STAGE, container_name=settings.container)
    n = 0
    for src in EXTENT_SOURCES:
        s = settings.blob_path(
            "silver", *source_segments(src, eid), "analysed_extent.parquet", event=eid
        )
        if not cc.get_blob_client(s).exists():
            # absence is a real per-event state (source not harmonized for this
            # event), not a failure — report it as information and move on.
            print(f"  skip {src}: no analysed_extent for {eid}", flush=True)
            continue
        d = _gold("extent", f"source={src}.parquet")
        kb = _copy(fs, settings, s, d) / 1e3
        print(f"  serving <- {d}  ({kb:.0f} KB)", flush=True)
        n += 1

    s = settings.blob_path(
        "silver", *source_segments("copernicus_ems", eid), "coverage_detail.parquet", event=eid
    )
    d = _gold("coverage_detail.parquet")
    kb = _copy(fs, settings, s, d) / 1e3
    print(f"  serving <- {d}  ({kb:.0f} KB)", flush=True)
    n += 1

    ledger.record(
        "common",
        "gold",
        f"server-rendered serving geometries staged to tiered gold — {ev.name} (ADR-0016)",
        settings.blob_path("gold", *common_segments(eid, adm0), "serving", event=eid),
        f"{n} files: per-source analysed_extent + CEMS coverage_detail; closes the "
        "silver serving leak so these layers are promote-gated",
    )
    print(f"done: {n} serving files staged to gold.", flush=True)


if __name__ == "__main__":
    main()
