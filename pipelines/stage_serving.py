"""Stage the server-rendered serving geometries into the tiered gold layer (ADR-0016).

A few layers are server-rendered — the FastAPI reads blob and returns GeoJSON — and
read SILVER, which the prod/dev split (ADR-0014) does NOT tier. So a dev harmonize
changes prod for those layers with no promote (that's how the IMPACT v2 AOI outline
leaked to prod ahead of the numbers). This copies those served geometries **verbatim**
(schema preserved) from silver into ``gold/model=common/adm0=VE/serving/``, where the
loaders now read them — ``az_path("gold")`` resolves to ``gold-prod`` on the prod
slot, so the reads become promote-gated like the rest of the served tier.

Staged (verbatim):
  * per-source ``analysed_extent`` (impact_initiatives, osu, microsoft, copernicus_ems)
    -> serving/extent/source=<src>.parquet
  * CEMS ``coverage_detail`` -> serving/coverage_detail.parquet

Run after the harmonizers, before ``promote.py``. See ADR-0016.
Run: uv run --group etl python pipelines/stage_serving.py
"""

from __future__ import annotations

import ocha_stratus as stratus

from gie import blobio, events, ledger
from gie.config import load_settings

ADM0, STAGE = "VE", "dev"
EVENT = "20260624-ve-earthquake"  # validated against events.yaml in main()
# Sources whose analysed_extent outline is server-rendered (hot_osm has none).
EXTENT_SOURCES = ["impact_initiatives", "osu", "microsoft", "copernicus_ems", "disha", "list"]


def _copy(fs, settings, src_blob: str, dest_blob: str) -> int:
    data = stratus.load_blob_data(src_blob, stage=STAGE, container_name=settings.container)
    blobio.upload(fs, data, dest_blob)
    return len(data)


def _gold(settings, *parts: str) -> str:
    return settings.blob_path("gold", "model=common", f"adm0={ADM0}", "serving", *parts, event=EVENT)


def main() -> None:
    events.require_event(EVENT)
    settings = load_settings(STAGE)
    fs = blobio.uploader(settings)
    n = 0

    for src in EXTENT_SOURCES:
        s = settings.blob_path(
            "silver", f"source={src}", f"adm0={ADM0}", "analysed_extent.parquet", event=EVENT
        )
        d = _gold(settings, "extent", f"source={src}.parquet")
        try:
            kb = _copy(fs, settings, s, d) / 1e3
            print(f"  serving <- {d}  ({kb:.0f} KB)", flush=True)
            n += 1
        except Exception as e:  # noqa: BLE001 — a source may not have an extent yet
            print(f"  skip {src} (no analysed_extent?): {str(e)[:60]}", flush=True)

    s = settings.blob_path(
        "silver", "source=copernicus_ems", f"adm0={ADM0}", "coverage_detail.parquet", event=EVENT
    )
    d = _gold(settings, "coverage_detail.parquet")
    kb = _copy(fs, settings, s, d) / 1e3
    print(f"  serving <- {d}  ({kb:.0f} KB)", flush=True)
    n += 1

    ledger.record(
        "common",
        "gold",
        "server-rendered serving geometries staged to tiered gold (ADR-0016)",
        settings.blob_path("gold", "model=common", f"adm0={ADM0}", "serving", event=EVENT),
        f"{n} files: per-source analysed_extent + CEMS coverage_detail; closes the "
        "silver serving leak so these layers are promote-gated",
    )
    print(f"done: {n} serving files staged to gold.", flush=True)


if __name__ == "__main__":
    main()
