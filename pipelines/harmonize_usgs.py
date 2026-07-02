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

Run: uv run --group etl python pipelines/harmonize_usgs.py
"""

from __future__ import annotations

import json

import ocha_stratus as stratus

from gie import ledger
from gie.config import load_settings

SOURCE = "usgs"
ADM0 = "VE"
STAGE = "dev"
EVENT = "us6000t7zp"  # M7.5 mainshock (the M7.2 foreshock us6000t7zc is bronze-only)


def main() -> None:
    settings = load_settings(STAGE)
    b = settings.blob_path("bronze", f"source={SOURCE}", f"adm0={ADM0}", f"event={EVENT}")

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
            "event": EVENT, "shakemap_version": smv,
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

    silver = settings.blob_path("silver", f"source={SOURCE}", f"adm0={ADM0}", "shakemap.geojson")
    platinum = settings.blob_path("platinum", "usgs", "shakemap.geojson")
    for dest in (silver, platinum):
        stratus.upload_blob_data(fc, dest, stage=STAGE, container_name=settings.container,
                                 content_type="application/geo+json")
        print(f"  <- {dest}  ({len(feats)} features {kinds})", flush=True)

    ledger.record(
        SOURCE, "silver",
        f"USGS M{p.get('mag')} ShakeMap viz — epicenter + MMI contours + rupture ({EVENT})",
        silver, f"{len(feats)} features {kinds}; EPSG:4326; ShakeMap v{smv}; served at platinum/usgs/ (not analytic)",
    )


if __name__ == "__main__":
    main()
