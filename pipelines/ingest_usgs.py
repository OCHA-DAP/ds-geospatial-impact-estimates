"""Loader: USGS ComCat + ShakeMap -> bronze (seismological viz layer).

NOT an analytic damage source — a context layer for the map: the official
epicenter and MMI (Modified Mercalli Intensity) shaking contours from USGS, the
authoritative source-of-record. Per event we land, as received:
  - event.geojson : the ComCat event (epicenter origin lon/lat/depth, magnitude, time)
  - cont_mi.json  : ShakeMap MMI intensity contour lines (MMI 3-8, with official colors)
  - rupture.json  : finite-fault rupture geometry, where present

USGS revises ShakeMap as the origin is refined; the event.geojson records the
current version, so re-running re-pulls the latest. Deterministic, no analysis.

Registry-driven, one event per run (ADR-0027): ``--event <event_id>`` — the
ComCat ids come from the event's ``external_ids`` (``usgs`` = mainshock,
optional ``usgs_foreshock``).

Run: uv run --group etl python pipelines/ingest_usgs.py --event 20260810-co-earthquake
"""

from __future__ import annotations

import argparse
import json
import urllib.request

from gie import blobio, events, ledger
from gie.config import load_settings, source_segments

API = "https://earthquake.usgs.gov/fdsnws/event/1/query"
# ShakeMap contents to grab for the viz: MMI contours + fault rupture geometry.
SM_PRODUCTS = ["download/cont_mi.json", "download/rupture.json"]
SOURCE = "usgs"
STAGE = "dev"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--event", required=True, help="event_id from events.yaml; ComCat ids from external_ids"
    )
    args = parser.parse_args(argv)
    event = events.get_event(args.event)  # fails loudly on an unregistered event
    comcat = [event.external_ids.get("usgs"), event.external_ids.get("usgs_foreshock")]
    comcat = [c for c in comcat if c]
    if not comcat:
        raise RuntimeError(
            f"event {event.event_id!r} has no external_ids.usgs in events.yaml — "
            "register the ComCat id before ingesting."
        )
    settings = load_settings(STAGE)
    fs = blobio.uploader(settings)

    for eid in comcat:
        raw = _get(f"{API}?eventid={eid}&format=geojson")
        ev = json.loads(raw)
        props = ev.get("properties", {})
        mag = props.get("mag")
        coords = (ev.get("geometry") or {}).get("coordinates")
        base = settings.blob_path(
            "bronze", *source_segments(SOURCE, event.event_id), f"event={eid}",
            event=event.event_id,
        )

        blobio.upload(fs, raw, f"{base}/event.geojson")
        landed = ["event.geojson"]
        sm = (props.get("products", {}).get("shakemap") or [{}])[0]
        contents = sm.get("contents", {})
        for prod in SM_PRODUCTS:
            c = contents.get(prod)
            if not c:
                continue
            blobio.upload(fs, _get(c["url"]), f"{base}/{prod.split('/')[-1]}")
            landed.append(prod.split("/")[-1])

        smv = sm.get("properties", {}).get("version")
        print(f"  USGS {eid} M{mag} epicenter {coords[:2] if coords else '?'} "
              f"ShakeMap v{smv}: {landed}", flush=True)
        ledger.record(
            SOURCE,
            "bronze",
            f"USGS ComCat + ShakeMap — {eid} (M{mag}, {props.get('place')})",
            base,
            f"epicenter {coords}; {', '.join(landed)}; ShakeMap v{smv}; "
            f"seismological viz layer (not an analytic source)",
        )


if __name__ == "__main__":
    main()
