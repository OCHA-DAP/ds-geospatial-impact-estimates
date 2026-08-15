"""Harmonize USGS ShakeMap (M7.5 mainshock) -> a serving GeoJSON viz layer.

Combines the M7.5 mainshock (us6000t7zp) epicenter, MMI intensity contours, and
finite-fault rupture into ONE FeatureCollection tagged by `kind`
(epicenter / contour / rupture), for the client to draw as a single "seismic
context" layer. The M7.2 foreshock (us6000t7zc) stays in bronze only — the M7.5
is the reference event for every damage source in this viewer.

Not an analytic source (no gold): the ShakeMap is context geometry, not facts, so
there is nothing to aggregate onto the Overture base. We write:
  - silver/source=usgs/.../shakemap.geojson   — the standardized artifact
  - platinum/usgs/shakemap.geojson            — the client-read serving copy
    (the client SAS is scoped to platinum/; promote.py copies the whole
    platinum/ tree, so this rides to prod like everything else). Tiny (~50 KB),
    so it's plain GeoJSON, not PMTiles. EPSG:4326 throughout.

Registry-driven, one event per run (ADR-0027): ``--event <event_id>`` — the
mainshock ComCat id comes from the event's ``external_ids.usgs`` (same real-world
earthquake, two id namespaces: USGS's own vs. this repo's registry).

Run: uv run --group etl python pipelines/harmonize_usgs.py --event 20260810-co-earthquake
"""

from __future__ import annotations

import argparse
import json

import ocha_stratus as stratus

from gie import events, ledger
from gie.config import load_settings, source_segments

SOURCE = "usgs"
STAGE = "dev"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--event", required=True,
        help="event_id from events.yaml; mainshock from external_ids.usgs",
    )
    args = parser.parse_args(argv)
    ev_reg = events.get_event(args.event)  # fails loudly on an unregistered event
    mainshock = ev_reg.external_ids.get("usgs")
    if not mainshock:
        raise RuntimeError(
            f"event {ev_reg.event_id!r} has no external_ids.usgs in events.yaml."
        )
    EVENT = ev_reg.event_id
    settings = load_settings(STAGE)
    b = settings.blob_path(
        "bronze", *source_segments(SOURCE, EVENT), f"event={mainshock}", event=EVENT
    )

    def _read(name: str) -> dict:
        return json.loads(
            stratus.load_blob_data(f"{b}/{name}", stage=STAGE, container_name=settings.container)
        )

    ev = _read("event.geojson")
    p = ev.get("properties", {})
    coords = (ev.get("geometry") or {}).get("coordinates", [])
    smv = ((p.get("products", {}).get("shakemap") or [{}])[0].get("properties", {})).get("version")

    feats: list[dict] = []
    # Epicenter (the ★)
    feats.append({
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": coords[:2]},
        "properties": {
            "kind": "epicenter", "mag": p.get("mag"),
            "depth_km": coords[2] if len(coords) > 2 else None,
            "place": p.get("place"), "time": p.get("time"),
            "event": mainshock, "shakemap_version": smv,
        },
    })
    # MMI intensity contours (colors baked in by USGS)
    for f in _read("cont_mi.json").get("features", []):
        pr = f.get("properties", {})
        feats.append({
            "type": "Feature", "geometry": f["geometry"],
            "properties": {"kind": "contour", "mmi": pr.get("value"),
                           "color": pr.get("color"), "weight": pr.get("weight")},
        })
    # Finite-fault rupture trace
    for f in _read("rupture.json").get("features", []):
        if f.get("geometry"):
            feats.append({"type": "Feature", "geometry": f["geometry"],
                          "properties": {"kind": "rupture"}})

    fc = json.dumps({"type": "FeatureCollection", "features": feats}).encode()
    kinds: dict[str, int] = {}
    for f in feats:
        k = f["properties"]["kind"]
        kinds[k] = kinds.get(k, 0) + 1

    silver = settings.blob_path(
        "silver", *source_segments(SOURCE, EVENT), "shakemap.geojson", event=EVENT
    )
    platinum = settings.blob_path("platinum", "usgs", "shakemap.geojson", event=EVENT)
    for dest in (silver, platinum):
        stratus.upload_blob_data(fc, dest, stage=STAGE, container_name=settings.container,
                                 content_type="application/geo+json")
        print(f"  <- {dest}  ({len(feats)} features {kinds})", flush=True)

    ledger.record(
        SOURCE, "silver",
        f"USGS M{p.get('mag')} ShakeMap viz — epicenter + MMI contours + rupture ({mainshock})",
        silver,
        f"{len(feats)} features {kinds}; EPSG:4326; ShakeMap v{smv}; "
        "served at platinum/usgs/ (not analytic)",
    )


if __name__ == "__main__":
    main()
