"""Sense-check viewer: writes self-contained HTML maps of the gold labels
so the team can eyeball what the pipeline produced before sharing it.

  --overview            corpus map: every label set as a rectangle, with
                        popups (event, day, sensor, method, area) and links
  --codes EMSR871,...   per-event maps: flood extent per acquisition (toggle
                        layers), valid mask, popups with the index row

Output: {out}/cems_labels_overview.html and {out}/{code}.html. Local files,
Leaflet + OSM basemap from public CDNs; data inlined; nothing is uploaded.

Run:  uv run --group etl --group api python pipelines/cems_flood/inspect_labels.py --codes EMSR871
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import common
import geopandas as gpd
import pandas as pd

GOLD = "copernicus_ems/flood/gold"

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#map{{height:100%;margin:0}}
.info{{position:absolute;top:10px;right:10px;z-index:1000;background:#fff;padding:8px 12px;
border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.3);font:13px/1.4 system-ui;max-width:340px}}
</style></head><body>
<div id="map"></div><div class="info">{info}</div>
<script>
const map = L.map('map');
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
  {{attribution:'&copy; OpenStreetMap · labels &copy; European Union, Copernicus EMS'}}).addTo(map);
{script}
</script></body></html>"""


def overview(idx: pd.DataFrame, out: Path) -> Path:
    feats = []
    for r in idx.itertuples():
        feats.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [r.minx, r.miny],
                            [r.maxx, r.miny],
                            [r.maxx, r.maxy],
                            [r.minx, r.maxy],
                            [r.minx, r.miny],
                        ]
                    ],
                },
                "properties": {
                    "p": f"<b>{r.code}</b> {r.name or ''}<br>{r.aoi} · {r.label_day or 'window'}"
                    f"<br>{r.sensor or '?'} · {r.acq_method} · {r.area_km2} km²",
                },
            }
        )
    script = f"""
const gj = {json.dumps({"type": "FeatureCollection", "features": feats})};
const layer = L.geoJSON(gj, {{style: {{color:'#0f62a8', weight:1, fillOpacity:.12}},
  onEachFeature: (f, l) => l.bindPopup(f.properties.p)}}).addTo(map);
map.fitBounds(layer.getBounds());
"""
    info = (
        f"<b>CEMS flood label corpus</b><br>{len(idx):,} label sets · "
        f"{idx.code.nunique()} activations · 2012–2026<br>"
        "Each rectangle is one (AOI, acquisition) label set. Click for details."
    )
    dest = out / "cems_labels_overview.html"
    dest.write_text(PAGE.format(title="CEMS flood labels overview", info=info, script=script))
    return dest


def event_map(cc, idx: pd.DataFrame, code: str, out: Path) -> Path:
    raw = cc.download_blob(f"{GOLD}/labels/code={code}/data.parquet").readall()
    lab = gpd.read_parquet(io.BytesIO(raw)).sort_values(["aoi", "acq_start"])
    meta = idx[idx.code == code].set_index(["aoi", "acq_start"])
    groups = []
    for r in lab.itertuples():
        m = meta.loc[(r.aoi, r.acq_start)] if (r.aoi, r.acq_start) in meta.index else None
        name = f"{r.aoi} · {str(r.acq_start)[:16]}"
        popup = f"<b>{code}</b> {name}<br>" + (
            f"{m.sensor or '?'} · {m.acq_method} · {m.area_km2} km²" if m is not None else ""
        )
        flood = json.loads(gpd.GeoSeries([r.geometry], crs="EPSG:4326").simplify(1e-4).to_json())
        valid = (
            json.loads(gpd.GeoSeries([r.valid_geometry], crs="EPSG:4326").simplify(5e-4).to_json())
            if r.valid_geometry is not None
            else None
        )
        groups.append({"name": name, "popup": popup, "flood": flood, "valid": valid})
    flood_style = "{style: {color:'#0f62a8', weight:1, fillOpacity:.45}}"
    valid_style = "{style: {color:'#666', weight:1, dashArray:'4 3', fillOpacity:.03}}"
    script_parts = ["const overlays = {};"]
    for i, g in enumerate(groups):
        script_parts.append(
            f"const fl{i} = L.geoJSON({json.dumps(g['flood'])}, {flood_style})"
            f".bindPopup({json.dumps(g['popup'])});"
        )
        if g["valid"]:
            script_parts.append(
                f"const va{i} = L.geoJSON({json.dumps(g['valid'])}, {valid_style});\n"
                f"overlays[{json.dumps(g['name'] + ' · valid mask')}] = va{i};"
            )
        script_parts.append(f"overlays[{json.dumps(g['name'])}] = fl{i};")
    script_parts.append("""
const first = Object.values(overlays)[Object.keys(overlays).length > 1 ? 1 : 0];
let bounds = null;
for (const l of Object.values(overlays)) { const b = L.geoJSON(l.toGeoJSON()).getBounds();
  bounds = bounds ? bounds.extend(b) : b; }
Object.values(overlays).forEach(l => l.addTo(map));
L.control.layers(null, overlays, {collapsed:false}).addTo(map);
map.fitBounds(bounds);""")
    n = len(groups)
    info = (
        f"<b>{code}</b> — {meta.iloc[0]['name'] if len(meta) else ''}<br>{n} label sets. "
        "Blue = observed flood extent; dashed grey = valid (analysed) mask. "
        "Toggle layers to step through acquisitions."
    )
    dest = out / f"{code}.html"
    dest.write_text(
        PAGE.format(title=f"{code} flood labels", info=info, script="\n".join(script_parts))
    )
    return dest


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--codes", default=None)
    ap.add_argument("--overview", action="store_true")
    ap.add_argument("--stage", default="dev", choices=["dev", "prod"])
    ap.add_argument("--out", default="/tmp/gie_cems_flood_maps", type=Path)
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    import ocha_stratus as stratus

    cc = stratus.get_container_client(container_name=common.CONTAINER, stage=args.stage)
    idx = pd.read_parquet(io.BytesIO(cc.download_blob(f"{GOLD}/label_index.parquet").readall()))
    if args.overview or not args.codes:
        print("wrote", overview(idx, args.out))
    for code in args.codes.split(",") if args.codes else []:
        print("wrote", event_map(cc, idx, code.strip(), args.out))


if __name__ == "__main__":
    main()
