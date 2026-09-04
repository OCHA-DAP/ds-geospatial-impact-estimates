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
# ruff: noqa: E501  (inline HTML/JS templates; line breaks would hurt readability)

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


EVENT_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
html,body{{height:100%;margin:0;font:14px/1.45 system-ui}}
#wrap{{display:flex;height:100%}}
#map{{flex:1}}
#side{{width:320px;padding:14px 16px;overflow-y:auto;border-right:1px solid #ddd;background:#fafafa}}
h1{{font-size:1.1rem;margin:0 0 2px}} .sub{{color:#666;font-size:.85rem;margin-bottom:12px}}
select,button{{font:inherit;padding:5px 9px;border-radius:6px;border:1px solid #bbb;background:#fff;cursor:pointer}}
#nav{{display:flex;gap:8px;align-items:center;margin:12px 0}}
#step{{font-weight:600}}
.meta{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:10px 12px;margin:10px 0;font-size:.9rem}}
.meta b{{font-size:1.05rem}}
label{{display:block;margin:6px 0;font-size:.9rem;cursor:pointer}}
.hint{{color:#888;font-size:.8rem;margin-top:14px}}
</style></head><body>
<div id="wrap">
<div id="side">
  <h1>{code}</h1><div class="sub">{name}</div>
  <div>AOI: <select id="aoi"></select></div>
  <div id="nav"><button id="prev">&#9664;</button><span id="step"></span><button id="next">&#9654;</button></div>
  <div class="meta" id="meta"></div>
  <label><input type="checkbox" id="ghost" checked> ghost previous extent (orange outline)</label>
  <label><input type="checkbox" id="mask"> show valid (analysed) mask</label>
  <div class="hint">Arrow keys step through acquisitions. Blue fill = observed
  flood extent for the shown acquisition. Data: gold/labels (dev).</div>
</div>
<div id="map"></div>
</div>
<script>
const DATA = __EVDATA__;
const map = L.map('map');
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
  {{attribution:'&copy; OpenStreetMap · labels &copy; European Union, Copernicus EMS'}}).addTo(map);
let cur = 0, layers = [];
const aoiSel = document.getElementById('aoi');
Object.keys(DATA).forEach(a => aoiSel.add(new Option(a, a)));
function clearLayers() {{ layers.forEach(l => map.removeLayer(l)); layers = []; }}
function render(fit) {{
  clearLayers();
  const steps = DATA[aoiSel.value];
  cur = Math.max(0, Math.min(cur, steps.length - 1));
  const s = steps[cur];
  if (document.getElementById('mask').checked && s.valid)
    layers.push(L.geoJSON(s.valid, {{style: {{color:'#777', weight:1, dashArray:'4 3', fillOpacity:.04}}}}).addTo(map));
  if (document.getElementById('ghost').checked && cur > 0)
    layers.push(L.geoJSON(steps[cur-1].flood, {{style: {{color:'#d97706', weight:1.5, fill:false, dashArray:'2 4'}}}}).addTo(map));
  const fl = L.geoJSON(s.flood, {{style: {{color:'#0f62a8', weight:1, fillOpacity:.5}}}}).addTo(map);
  layers.push(fl);
  document.getElementById('step').textContent = (cur+1) + ' / ' + steps.length;
  document.getElementById('meta').innerHTML =
    '<b>' + s.dt + '</b><br>' + (s.sensor || 'sensor unknown') + ' · ' + s.method +
    '<br>' + s.area + ' km² observed' + (s.products ? '<br>' + s.products : '');
  if (fit) map.fitBounds(L.geoJSON(steps[steps.length-1].flood).getBounds().pad(0.4));
}}
aoiSel.onchange = () => {{ cur = 0; render(true); }};
document.getElementById('prev').onclick = () => {{ cur--; render(false); }};
document.getElementById('next').onclick = () => {{ cur++; render(false); }};
document.getElementById('ghost').onchange = () => render(false);
document.getElementById('mask').onchange = () => render(false);
document.addEventListener('keydown', e => {{
  if (e.key === 'ArrowLeft') {{ cur--; render(false); }}
  if (e.key === 'ArrowRight') {{ cur++; render(false); }}
}});
render(true);
</script></body></html>"""


def _gj(geom, tol: float) -> dict:
    from shapely import set_precision

    g = set_precision(geom.simplify(tol), 1e-5)
    return json.loads(gpd.GeoSeries([g], crs="EPSG:4326").to_json())


def event_map(cc, idx: pd.DataFrame, code: str, out: Path) -> Path:
    raw = cc.download_blob(f"{GOLD}/labels/code={code}/data.parquet").readall()
    lab = gpd.read_parquet(io.BytesIO(raw)).sort_values(["aoi", "acq_start"])
    meta = idx[idx.code == code].set_index(["aoi", "acq_start"])
    data: dict[str, list] = {}
    for r in lab.itertuples():
        m = meta.loc[(r.aoi, r.acq_start)] if (r.aoi, r.acq_start) in meta.index else None
        data.setdefault(r.aoi, []).append(
            {
                "dt": str(r.acq_start)[:16] if pd.notna(r.acq_start) else "window",
                "sensor": (None if m is None or pd.isna(m.sensor) else m.sensor),
                "method": "" if m is None else m.acq_method,
                "area": 0 if m is None else m.area_km2,
                "products": "" if m is None else m.product_classes,
                "flood": _gj(r.geometry, 1e-4),
                "valid": _gj(r.valid_geometry, 5e-4) if r.valid_geometry is not None else None,
            }
        )
    name = meta.iloc[0]["name"] if len(meta) else ""
    # format() first (the JSON payload is full of braces), then inject data
    html = EVENT_PAGE.format(title=f"{code} flood labels", code=code, name=name)
    html = html.replace("__EVDATA__", json.dumps(data))
    dest = out / f"{code}.html"
    dest.write_text(html)
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
