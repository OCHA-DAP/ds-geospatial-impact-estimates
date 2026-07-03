import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";
import maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import { asyncBufferFromUrl, parquetReadObjects } from "hyparquet";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";
import { H3HexagonLayer } from "@deck.gl/geo-layers";

type RGBA = [number, number, number, number];

const SOURCE_LABEL: Record<string, string> = {
  microsoft: "Microsoft",
  copernicus_ems: "Copernicus EMS",
  impact_initiatives: "IMPACT SAR (proxy)",
  hot_osm: "HotOSM",
  osu: "OSU S1 (coherence)",
  disha: "DISHA (zero-shot)",
};
const SOURCE_COLOR: Record<string, [number, number, number]> = {
  microsoft: [40, 110, 205],
  copernicus_ems: [235, 125, 20],
  impact_initiatives: [150, 70, 190],
  hot_osm: [210, 45, 130],
  osu: [20, 160, 130],
  disha: [225, 200, 40],
};

const state = {
  sources: new Set<string>(),
  view: "overture", // "overture" | "native"
  metric: "damage_rate_detected",
  adminLevel: 3,
  show: { admin: true, buildings: false, extent: true, h3: false } as Record<string, boolean>,
};

let METRICS: { key: string; label: string }[] = [];
const adminCache = new Map<string, any>();
const h3Cache = new Map<string, any[]>();
const buildingsCache = new Map<string, any[]>();
const nativeCache = new Map<string, any>();
const extentCache = new Map<string, any>();
let coverageDetailData: any = null; // CEMS AOI + not-analysed (cloud) shapes
let agreementData: any[] | null = null;

// Source-agreement categories (the spatial Venn) — used by the "agreement" view.
const AGREEMENT: Record<string, { label: string; color: [number, number, number] }> = {
  both: { label: "Both damaged", color: [150, 25, 40] },
  ms_only: { label: "Microsoft only", color: [40, 110, 205] },
  cems_only: { label: "Copernicus only", color: [235, 125, 20] },
  agree_none: { label: "Agree: undamaged", color: [165, 170, 178] },
};
function agreementColor(cat: string): RGBA {
  const o = AGREEMENT[cat];
  if (o) return [...o.color, cat === "agree_none" ? 110 : 235] as RGBA;
  return cat === "ms_area" ? [40, 110, 205, 28] : [235, 125, 20, 28]; // single-source = faint
}

function extentTip(s: string, p: any): string {
  const src = SOURCE_LABEL[s] ?? s;
  if (s === "copernicus_ems") {
    const acq = p.acquired && p.acquired !== "—" ? ` · ${p.acquired}` : "";
    return `${src} coverage<br>${p.aoi_name ?? "?"} · ${p.product ?? ""}${acq}`;
  }
  return `${src} coverage<br>${p.aoi_name ?? ""}`;
}

const map = new maplibregl.Map({
  container: "map",
  style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  center: [-67.03, 10.59],
  zoom: 11,
});
const overlay = new MapboxOverlay({ interleaved: false, layers: [] });
map.addControl(overlay as any);

// --- v2 serving: EXPLICIT per-layer registry (no silent fallback). Each native
// source is served from PMTiles (converted) or deck.gl (not yet). A converted
// source declares its own MapLibre layer spec(s) + hover, mirroring the deck.gl
// look. Flip a source from "deckgl" to "pmtiles" once its tiles + styling exist.
//
// CEMS damage colour ramp by class (1 possibly .. 3 destroyed) — the discrete
// values match the deck.gl damageColor(max(0.25, class/3)) the native view used.
// Distinct hues per grade (amber -> orange -> red) so the three classes read
// clearly even at the coarse blocks' low opacity — not just lightness steps.
const DAMAGE_BY_CLASS: any = [
  "match",
  ["get", "damage_class"],
  1, "rgb(255,199,64)",
  2, "rgb(240,124,32)",
  3, "rgb(202,24,24)",
  "rgb(225,60,40)",
];
type PmLayer = { id: string; spec: any };
type Serving =
  | { mode: "pmtiles"; file: string; sourceLayer: string; layers: PmLayer[]; hover: (p: any) => string }
  | { mode: "deckgl" };

const LAYER_SERVING: Record<string, Serving> = {
  microsoft: {
    mode: "pmtiles",
    file: "native-microsoft/footprints.pmtiles",
    sourceLayer: "footprints",
    layers: [
      {
        id: "pmt-microsoft",
        spec: {
          type: "fill",
          paint: {
            "fill-color": ["case", ["==", ["get", "damaged"], 1], "#dc1e1e", "#788090"],
            "fill-opacity": ["case", ["==", ["get", "damaged"], 1], 0.8, 0.28],
          },
        },
      },
    ],
    hover: (p) => `Microsoft footprint<br>damaged: ${p.damaged ? "yes" : "no"}`,
  },
  copernicus_ems: {
    mode: "pmtiles",
    file: "native-cems/builtup_damage.pmtiles",
    sourceLayer: "builtup_damage",
    // Mirror load_native: latest per-building POINTS + ALL coarse AREA blocks.
    // Areas = translucent fills, points = solid circles — like the deck.gl view.
    layers: [
      {
        id: "pmt-cems-area",
        spec: {
          type: "fill",
          filter: ["==", ["get", "layer_type"], "area"],
          paint: { "fill-color": DAMAGE_BY_CLASS, "fill-opacity": 0.32 },
        },
      },
      {
        id: "pmt-cems-point",
        spec: {
          type: "circle",
          filter: ["all", ["==", ["get", "layer_type"], "point"], ["get", "is_latest"]],
          paint: {
            "circle-color": DAMAGE_BY_CLASS,
            "circle-opacity": 0.85,
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 3, 15, 7],
            "circle-stroke-width": 0,
          },
        },
      },
    ],
    hover: (p) =>
      `Copernicus EMS<br>grade: ${p.ems_grade}` +
      (p.layer_type
        ? `<br>${p.layer_type === "area" ? "coarse block (early estimate)" : "per-building point"}`
        : ""),
  },
  impact_initiatives: { mode: "deckgl" },
  osu: { mode: "deckgl" },
  disha: {
    mode: "pmtiles",
    file: "native-disha/damage_points.pmtiles",
    sourceLayer: "damage_points",
    layers: [
      {
        id: "pmt-disha",
        spec: {
          type: "circle",
          paint: {
            "circle-color": DAMAGE_BY_CLASS,
            "circle-opacity": 0.85,
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 3, 15, 7],
            "circle-stroke-width": 0,
          },
        },
      },
    ],
    hover: (p) =>
      `${SOURCE_LABEL["disha"] ?? "disha"}<br>grade: ${p.ems_grade}` +
      (p.score != null ? `<br>score: ${Math.round(p.score * 100)}%` : ""),
  },
  hot_osm: {
    mode: "pmtiles",
    file: "native-hot_osm/damage_points.pmtiles",
    sourceLayer: "damage_points",
    layers: [
      {
        id: "pmt-hot",
        spec: {
          type: "circle",
          paint: {
            "circle-color": DAMAGE_BY_CLASS,
            "circle-opacity": 0.85,
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 3, 15, 7],
            "circle-stroke-width": 0,
          },
        },
      },
    ],
    hover: (p) =>
      `${SOURCE_LABEL["hot_osm"] ?? "hot_osm"}<br>grade: ${p.ems_grade}` +
      (p.confidence != null ? `<br>confidence: ${Math.round(p.confidence * 100)}%` : ""),
  },
};
const usePmtiles = (s: string) => LAYER_SERVING[s]?.mode === "pmtiles";

// Overture/buildings view: ONE building_flags PMTiles (every source's flags
// embedded) serves all sources' points — viewport-streamed, no per-source fetch.
const OVERTURE_SERVING: "pmtiles" | "deckgl" = "pmtiles";
const BUILDING_FIELDS: Record<string, { seen: string; dmg: string }> = {
  microsoft: { seen: "ms_analysed", dmg: "ms_dmg" },
  copernicus_ems: { seen: "cems_analysed", dmg: "cems_dmg" },
  impact_initiatives: { seen: "sar_dmg", dmg: "sar_dmg" }, // damaged-only (ADR-0008)
  osu: { seen: "osu_dmg", dmg: "osu_dmg" }, // damaged-only
  hot_osm: { seen: "hot_dmg", dmg: "hot_dmg" }, // detected-only
  disha: { seen: "disha_dmg", dmg: "disha_dmg" }, // damaged-only (LICENCE-gated)
};

// Add the one buildings tile + per-source exposed/damaged circle layers (hidden).
async function setupBuildings() {
  if (OVERTURE_SERVING !== "pmtiles") return;
  const tok = await fetch("/api/token").then((r) => r.json());
  const pdir = tok.platinum_dir || "platinum";
  map.addSource("pmt-src-buildings", {
    type: "vector",
    url: `pmtiles://${tok.base_url}/${pdir}/buildings/building_flags.pmtiles?${tok.sas}`,
  });
  for (const [s, f] of Object.entries(BUILDING_FIELDS)) {
    map.addLayer({
      id: `bpm-${s}-exposed`,
      source: "pmt-src-buildings",
      "source-layer": "building_flags",
      type: "circle",
      layout: { visibility: "none" },
      filter: ["all", ["get", f.seen], ["!", ["get", f.dmg]]],
      paint: {
        "circle-color": "rgb(110,118,130)",
        "circle-opacity": 0.34,
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 1, 15, 3],
        "circle-stroke-width": 0,
      },
    } as any);
    map.addLayer({
      id: `bpm-${s}-damaged`,
      source: "pmt-src-buildings",
      "source-layer": "building_flags",
      type: "circle",
      layout: { visibility: "none" },
      filter: ["all", ["get", f.seen], ["get", f.dmg]],
      paint: {
        "circle-color": "rgb(230,20,20)",
        "circle-opacity": 0.94,
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 2, 15, 6],
        "circle-stroke-width": 0,
      },
    } as any);
  }
}

// Show per-source building points only in the Overture view.
function syncBuildings() {
  if (OVERTURE_SERVING !== "pmtiles") return;
  const on = state.view === "overture" && state.show.buildings;
  for (const s of Object.keys(BUILDING_FIELDS)) {
    const show = on && state.sources.has(s);
    for (const suf of ["exposed", "damaged"]) {
      const id = `bpm-${s}-${suf}`;
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", show ? "visible" : "none");
    }
  }
}

// Admin choropleth (v2): boundaries from admin PMTiles, values from hyparquet,
// each unit coloured via setFeatureState. Reuses adminCache/byUnit/metricColor/
// adminTip — only the data source + render path change. Being a real MapLibre
// layer, it sits IN the stack (fixes the deck.gl "always on top of tiles" issue).
const ADMIN_SERVING: "pmtiles" | "deckgl" = "pmtiles";

async function setupAdmin() {
  if (ADMIN_SERVING !== "pmtiles") return;
  const tok = await fetch("/api/token").then((r) => r.json());
  const pdir = tok.platinum_dir || "platinum";
  // values: read the slim admin facts parquet, pivot into adminCache (properties
  // only — geometry comes from the tiles now) so the existing logic is reused.
  const rows = (await parquetReadObjects({
    file: await asyncBufferFromUrl({
      url: `${tok.base_url}/${pdir}/values/facts-admin.parquet?${tok.sas}`,
    }),
  })) as any[];
  const byKey = new Map<string, Map<string, any>>();
  for (const r of rows) {
    const lvl = Number(String(r.unit_type).replace("adm", ""));
    const k = `${r.source}:${lvl}`;
    let units = byKey.get(k);
    if (!units) byKey.set(k, (units = new Map()));
    let p = units.get(r.unit_id);
    if (!p) units.set(r.unit_id, (p = { unit_id: r.unit_id, unit_name: r.unit_name }));
    p[r.metric] = r.value;
  }
  for (const [k, units] of byKey)
    adminCache.set(k, { features: [...units.values()].map((p) => ({ properties: p })) });
  // boundaries: one vector source + fill/line per level (hidden until shown).
  // Insert BELOW the basemap labels so labels stay readable — this is the
  // layering the deck.gl admin (drawn over everything) couldn't do.
  const labelId = map.getStyle().layers?.find((l: any) => l.type === "symbol")?.id;
  for (const lvl of [1, 2, 3]) {
    const src = `pmt-src-admin-${lvl}`;
    const sl = `adm${lvl}`;
    map.addSource(src, {
      type: "vector",
      url: `pmtiles://${tok.base_url}/${pdir}/admin-adm${lvl}/adm${lvl}.pmtiles?${tok.sas}`,
      promoteId: `adm${lvl}_id`,
    });
    map.addLayer({
      id: `pmt-admin-${lvl}-fill`,
      source: src,
      "source-layer": sl,
      type: "fill",
      layout: { visibility: "none" },
      paint: {
        "fill-color": ["coalesce", ["feature-state", "color"], "rgba(0,0,0,0)"],
        "fill-opacity": 0.6,
      },
    } as any, labelId);
    map.addLayer({
      id: `pmt-admin-${lvl}-line`,
      source: src,
      "source-layer": sl,
      type: "line",
      layout: { visibility: "none" },
      paint: { "line-color": "rgb(55,65,80)", "line-width": 1, "line-opacity": 0.45 },
    } as any, labelId);
    map.on("mousemove", `pmt-admin-${lvl}-fill`, (e: any) => {
      const f = e.features?.[0];
      if (f)
        showTip(e.point.x, e.point.y, adminTip(f.properties[`adm${lvl}_id`], f.properties[`adm${lvl}_name`]));
    });
    map.on("mouseleave", `pmt-admin-${lvl}-fill`, hideTip);
  }
}

// Colour each unit by the max-across-sources value (byUnit, computed in buildLayers).
function applyAdminState(byUnit: Map<string, any>, m: string, aMax: number) {
  const lvl = state.adminLevel;
  const src = `pmt-src-admin-${lvl}`;
  const sl = `adm${lvl}`;
  map.removeFeatureState({ source: src, sourceLayer: sl });
  for (const [unitId, { v }] of byUnit) {
    const c = metricColor(m, v, aMax);
    map.setFeatureState({ source: src, sourceLayer: sl, id: unitId }, { color: `rgb(${c[0]},${c[1]},${c[2]})` });
  }
}

// Show only the active admin level's fill+line (when admin is on).
function syncAdmin() {
  if (ADMIN_SERVING !== "pmtiles") return;
  for (const lvl of [1, 2, 3]) {
    const vis = state.show.admin && state.sources.size && lvl === state.adminLevel ? "visible" : "none";
    for (const suf of ["fill", "line"]) {
      const id = `pmt-admin-${lvl}-${suf}`;
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis);
    }
  }
}

maplibregl.addProtocol("pmtiles", new Protocol().tile);

// Add each "pmtiles" source's MapLibre layers (hidden until shown by syncPmtiles)
// and wire their hover. The read SAS + catalog base URL come from /api/token.
async function setupPmtiles() {
  const converted = Object.entries(LAYER_SERVING).filter(([, v]) => v.mode === "pmtiles") as [
    string,
    Extract<Serving, { mode: "pmtiles" }>,
  ][];
  if (!converted.length) return;
  const tok = await fetch("/api/token").then((r) => r.json());
  const pdir = tok.platinum_dir || "platinum";
  for (const [s, v] of converted) {
    const src = `pmt-src-${s}`;
    map.addSource(src, { type: "vector", url: `pmtiles://${tok.base_url}/${pdir}/${v.file}?${tok.sas}` });
    for (const { id, spec } of v.layers) {
      map.addLayer({
        id,
        source: src,
        "source-layer": v.sourceLayer,
        layout: { visibility: "none" },
        ...spec,
      } as any);
      map.on("mousemove", id, (e: any) => {
        if (e.features?.[0]) showTip(e.point.x, e.point.y, v.hover(e.features[0].properties));
      });
      map.on("mouseleave", id, hideTip);
    }
  }
}

// Show a source's PMTiles layer(s) only when its native view is active.
function syncPmtiles() {
  for (const [s, v] of Object.entries(LAYER_SERVING)) {
    if (v.mode !== "pmtiles") continue;
    const show = state.view === "native" && state.show.buildings && state.sources.has(s);
    for (const { id } of v.layers) {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", show ? "visible" : "none");
    }
  }
}

// USGS seismic-context layer (M7.5 mainshock): MMI shaking contours + fault
// rupture + epicentre ★, all from one GeoJSON in platinum/usgs/. Toggled together.
const USGS_LAYERS = [
  "usgs-epi-glow", "usgs-contour-casing", "usgs-contour", "usgs-rupture", "usgs-contour-label",
  "usgs-epi-star", "usgs-epi-mag",
];
async function setupUsgs() {
  const tok = await fetch("/api/token").then((r) => r.json());
  const pdir = tok.platinum_dir || "platinum";
  map.addSource("usgs", {
    type: "geojson",
    data: `${tok.base_url}/${pdir}/usgs/shakemap.geojson?${tok.sas}`,
  });
  // A star icon for the epicentre (SVG → addImage, so it never depends on glyphs).
  await new Promise<void>((res) => {
    const svg =
      '<svg xmlns="http://www.w3.org/2000/svg" width="52" height="52" viewBox="0 0 24 24">' +
      '<path d="M12 1.3l2.94 6.36 6.96.86-5.14 4.74 1.36 6.88L12 17.7l-6.08 3.35 1.36-6.88' +
      '-5.14-4.74 6.96-.86z" fill="#e8112d" stroke="#fff" stroke-width="1.2" stroke-linejoin="round"/></svg>';
    const img = new Image(52, 52);
    img.onload = () => { if (!map.hasImage("epi-star")) map.addImage("epi-star", img); res(); };
    img.onerror = () => res();
    img.src = "data:image/svg+xml;base64," + btoa(svg);
  });
  const hidden = { visibility: "none" as const };
  map.addLayer({
    id: "usgs-epi-glow", source: "usgs", type: "circle", filter: ["==", ["get", "kind"], "epicenter"],
    layout: hidden,
    paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 16, 8, 52, 11, 100],
      "circle-color": "#e8112d", "circle-opacity": 0.22, "circle-blur": 0.9 },
  } as any);
  // White casing so the coloured contours read over the busy damage layers.
  map.addLayer({
    id: "usgs-contour-casing", source: "usgs", type: "line", filter: ["==", ["get", "kind"], "contour"],
    layout: { ...hidden, "line-cap": "round", "line-join": "round" },
    paint: { "line-color": "#ffffff", "line-opacity": 0.6,
      "line-width": ["interpolate", ["linear"], ["get", "mmi"], 3, 3, 6, 5, 8, 8.5] },
  } as any);
  map.addLayer({
    id: "usgs-contour", source: "usgs", type: "line", filter: ["==", ["get", "kind"], "contour"],
    layout: { ...hidden, "line-cap": "round", "line-join": "round" },
    paint: { "line-color": ["get", "color"], "line-opacity": 0.95,
      "line-width": ["interpolate", ["linear"], ["get", "mmi"], 3, 1.2, 6, 2.8, 8, 5.5] },
  } as any);
  map.addLayer({
    id: "usgs-rupture", source: "usgs", type: "line", filter: ["==", ["get", "kind"], "rupture"],
    layout: { ...hidden, "line-cap": "round" },
    paint: { "line-color": "#3a0a0a", "line-width": 2.5, "line-dasharray": [2, 1.2], "line-opacity": 0.75 },
  } as any);
  map.addLayer({
    id: "usgs-contour-label", source: "usgs", type: "symbol", filter: ["==", ["get", "kind"], "contour"],
    layout: { ...hidden, "symbol-placement": "line", "symbol-spacing": 350,
      "text-field": ["match", ["get", "mmi"], 3, "III", 4, "IV", 5, "V", 6, "VI", 7, "VII", 8, "VIII", 9, "IX", ""],
      "text-font": ["Open Sans Bold"], "text-size": 12 },
    paint: { "text-color": "#5a3b00", "text-halo-color": "#fff", "text-halo-width": 1.5 },
  } as any);
  map.addLayer({
    id: "usgs-epi-star", source: "usgs", type: "symbol", filter: ["==", ["get", "kind"], "epicenter"],
    layout: { ...hidden, "icon-image": "epi-star", "icon-size": 0.62, "icon-allow-overlap": true },
  } as any);
  map.addLayer({
    id: "usgs-epi-mag", source: "usgs", type: "symbol", filter: ["==", ["get", "kind"], "epicenter"],
    layout: { ...hidden, "text-field": ["concat", "M", ["to-string", ["get", "mag"]]],
      "text-font": ["Open Sans Bold"], "text-size": 13, "text-offset": [0, 1.6], "text-anchor": "top",
      "text-allow-overlap": true },
    paint: { "text-color": "#e8112d", "text-halo-color": "#fff", "text-halo-width": 2 },
  } as any);
  map.on("mousemove", "usgs-contour", (e: any) => {
    const p = e.features?.[0]?.properties; if (p) showTip(e.point.x, e.point.y, `Shaking intensity · MMI ${p.mmi}`);
  });
  map.on("mouseleave", "usgs-contour", hideTip);
  map.on("mousemove", "usgs-epi-star", (e: any) => {
    const p = e.features?.[0]?.properties;
    if (p) showTip(e.point.x, e.point.y, `Epicentre · M${p.mag}<br>${p.place}<br>depth ${p.depth_km} km`);
  });
  map.on("mouseleave", "usgs-epi-star", hideTip);
}

function syncUsgs() {
  const vis = state.show.usgs ? "visible" : "none";
  for (const id of USGS_LAYERS) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis);
}

// Optional satellite basemap (Esri World Imagery), drawn under the place labels.
const satEl = document.getElementById("satellite") as HTMLInputElement | null;
function applySatellite() {
  if (map.getLayer("satellite"))
    map.setLayoutProperty("satellite", "visibility", satEl?.checked ? "visible" : "none");
}
map.on("load", () => {
  map.addSource("satellite", {
    type: "raster",
    tiles: [
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    ],
    tileSize: 256,
    attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
  });
  const firstSymbol = map.getStyle().layers?.find((l: any) => l.type === "symbol")?.id;
  map.addLayer(
    { id: "satellite", type: "raster", source: "satellite", layout: { visibility: "none" } },
    firstSymbol,
  );
  applySatellite();
});
satEl?.addEventListener("change", applySatellite);

// --- colour ------------------------------------------------------------------
function damageColor(t: number | null | undefined): RGBA {
  if (t == null || Number.isNaN(t)) return [200, 200, 200, 35];
  const f = Math.max(0, Math.min(1, t));
  // pale cream (low) -> orange -> deep red (high)
  return [Math.round(250 - 28 * f), Math.round(244 - 214 * f), Math.round(208 - 188 * f), 210];
}
// pseudo-log (log1p) lift so low values separate clearly from zero
function lift(t: number): number {
  const k = 12;
  return Math.log1p(k * Math.max(0, Math.min(1, t))) / Math.log1p(k);
}
function metricValue(p: any, metric: string): number | null {
  // damage fraction = damaged / buildings in the source's VALID (analysed) area
  if (metric === "damage_rate_detected")
    return p.analysed_buildings ? p.damaged_detected / p.analysed_buildings : null;
  if (metric === "damage_rate_extrapolated")
    return p.exposed_buildings ? (p.damaged_extrapolated ?? 0) / p.exposed_buildings : null;
  return p[metric];
}
function metricColor(metric: string, value: number | null | undefined, max: number): RGBA {
  if (value == null || Number.isNaN(value)) return [200, 200, 200, 35];
  let t: number;
  if (metric === "coverage_fraction") t = 1 - Math.max(0, Math.min(1, value));
  else if (metric.startsWith("damage_rate")) t = Math.max(0, Math.min(1, value));
  else t = max ? value / max : 0;
  return damageColor(lift(t));
}
function nativeColor(source: string, p: any): RGBA {
  if (source === "microsoft") return p.damaged ? [220, 30, 30, 205] : [120, 128, 140, 70];
  const cls = p.damage_class; // CEMS: 1 possibly .. 3 destroyed
  const rgb = (cls == null ? [225, 60, 40, 0] : damageColor(Math.max(0.25, cls / 3))) as number[];
  // CEMS coarse area blocks (the earlier, lower-resolution estimate) render
  // translucent so the per-building point estimates read clearly on top of them.
  return [rgb[0], rgb[1], rgb[2], p.layer_type === "area" ? 60 : 210];
}
const maxBy = (arr: any[], get: (x: any) => number) =>
  Math.max(1, ...arr.map(get).filter((v) => !Number.isNaN(v)));
const hasCov = (p: any) => (p?.coverage_fraction ?? 0) > 0;

// --- tooltip -----------------------------------------------------------------
const tooltip = document.getElementById("tooltip")!;
function showTip(x: number, y: number, html: string) {
  // set content first so we can measure the rendered size, then place it so it
  // never runs off-screen: flip to the left of the cursor near the right edge,
  // above near the bottom, and clamp as a final guard (wide comparison card).
  tooltip.innerHTML = html;
  tooltip.style.display = "block";
  const pad = 14;
  const w = tooltip.offsetWidth;
  const h = tooltip.offsetHeight;
  let left = x + pad + w > window.innerWidth ? x - pad - w : x + pad;
  let top = y + pad + h > window.innerHeight ? y - pad - h : y + pad;
  left = Math.max(6, Math.min(left, window.innerWidth - w - 6));
  top = Math.max(6, Math.min(top, window.innerHeight - h - 6));
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}
const hideTip = () => {
  tooltip.style.display = "none";
};
const num = (n: any) => (n == null || Number.isNaN(n) ? "—" : Math.round(n).toLocaleString());
const pct = (n: any) => (n == null || Number.isNaN(n) ? "—" : `${(100 * n).toFixed(0)}%`);
const tip = (name: string, p: any) =>
  `<b>${name}</b><br>total buildings: ${num(p.exposed_buildings)}<br>coverage: ${pct(p.coverage_fraction)}<br>` +
  `analysed: ${num(p.analysed_buildings)}<br>` +
  `damaged: ${num(p.damaged_detected)}<br>` +
  `damage fraction: ${pct(p.analysed_buildings ? p.damaged_detected / p.analysed_buildings : null)}`;

// Hover card: a side-by-side comparison of every checked source that has data
// for this unit (it assessed the unit, or detected damage in it). Coverage-aware
// sources show coverage/analysed; detected-only sources (no AOI, e.g. HotOSM)
// show "—" there and a "(point)" damaged count. CEMS's per-grade point breakdown
// and coarse area estimate render as a footer.
function adminTip(unitId: any, unitName: string): string {
  const cols = [...state.sources]
    .map((s) => {
      const f = (adminCache.get(`${s}:${state.adminLevel}`)?.features ?? []).find(
        (x: any) => x.properties.unit_id === unitId,
      );
      return { s, p: f?.properties };
    })
    .filter((c) => c.p && (hasCov(c.p) || (c.p.damaged_detected ?? 0) > 0));
  if (!cols.length)
    return `<div class="tt-title">${unitName}</div><div class="tt-empty">no source data here</div>`;

  const isPoint = (s: string) => s === "copernicus_ems" || s === "hot_osm";
  const frac = (p: any) => (p.analysed_buildings ? p.damaged_detected / p.analysed_buildings : null);
  const head = cols.map((c) => `<th>${SOURCE_LABEL[c.s] ?? c.s}</th>`).join("");
  const fracRow = cols
    .map((c) => {
      const v = frac(c.p);
      const fill =
        v == null ? "" : `<div class="tt-fill" style="width:${Math.round(lift(v) * 100)}%"></div>`;
      return `<td><span class="tt-big">${pct(v)}</span><div class="tt-bar">${fill}</div></td>`;
    })
    .join("");
  const row = (label: string, cell: (p: any, s: string) => string) =>
    `<tr><td class="tt-rl">${label}</td>${cols.map((c) => `<td>${cell(c.p, c.s)}</td>`).join("")}</tr>`;

  let html =
    `<div class="tt-title">${unitName}</div>` +
    `<table class="tt"><tr class="tt-head"><th></th>${head}</tr>` +
    `<tr class="tt-frac"><td class="tt-rl">Damage fraction</td>${fracRow}</tr>` +
    `<tr class="tt-sep"><td colspan="${cols.length + 1}"></td></tr>` +
    row("Total buildings", (p) => num(p.exposed_buildings)) +
    row("Coverage", (p) => pct(p.coverage_fraction)) +
    row("Analysed", (p) => num(p.analysed_buildings)) +
    row(
      "Damaged",
      (p, s) => num(p.damaged_detected) + (isPoint(s) ? ` <span class="tt-note">(point)</span>` : ""),
    ) +
    `</table>`;

  const cems = cols.find((c) => c.s === "copernicus_ems")?.p;
  if (cems && ((cems.damaged_detected ?? 0) > 0 || (cems.cems_coarse_detected ?? 0) > 0)) {
    let foot = "";
    if ((cems.damaged_detected ?? 0) > 0)
      foot +=
        `<div class="tt-foot-h">Copernicus EMS point damage:</div>` +
        `<div class="tt-foot-l">${num(cems.cems_destroyed)} destroyed · ${num(cems.cems_damaged)} damaged · ${num(cems.cems_possibly)} possibly damaged</div>`;
    if ((cems.cems_coarse_detected ?? 0) > 0)
      foot += `<div class="tt-foot-h">Area-based estimate: ${num(cems.cems_coarse_detected)} buildings <span class="tt-note">(not point-counted)</span></div>`;
    html += `<div class="tt-foot">${foot}</div>`;
  }
  return html;
}

// --- layers ------------------------------------------------------------------
function buildLayers() {
  const m = state.metric;
  const sources = [...state.sources];
  const layers: any[] = [];

  const adminFeats = sources.flatMap((s) =>
    (adminCache.get(`${s}:${state.adminLevel}`)?.features ?? []).filter((f: any) => hasCov(f.properties)),
  );
  const aMax = maxBy(adminFeats, (f) => metricValue(f.properties, m) ?? 0);
  const h3All = sources.flatMap((s) => (h3Cache.get(s) ?? []).filter(hasCov));
  const hMax = maxBy(h3All, (r) => metricValue(r, m) ?? 0);

  // admin aggregation: ONE layer, each unit coloured by the MAX metric value across
  // the selected sources (recomputed as sources toggle). Hover shows the per-source
  // breakdown (adminTip), so you still see which source drove the max.
  if (state.show.admin && sources.length) {
    const byUnit = new Map<string, { f: any; v: number | null }>();
    for (const s of sources) {
      for (const f of adminCache.get(`${s}:${state.adminLevel}`)?.features ?? []) {
        if (!hasCov(f.properties)) continue;
        const v = metricValue(f.properties, m);
        const cur = byUnit.get(f.properties.unit_id);
        if (!cur) byUnit.set(f.properties.unit_id, { f, v });
        else if (v != null && (cur.v == null || v > cur.v)) {
          cur.f = f;
          cur.v = v;
        }
      }
    }
    if (ADMIN_SERVING === "pmtiles") {
      applyAdminState(byUnit, m, aMax); // colour the MapLibre admin layer in-place
    } else {
      const feats = [...byUnit.values()].map(({ f, v }) => ({
        ...f,
        properties: { ...f.properties, _v: v },
      }));
      layers.push(
        new GeoJsonLayer({
          id: `admin-${state.adminLevel}`,
          data: { type: "FeatureCollection", features: feats },
          pickable: true,
          filled: true,
          stroked: true,
          opacity: 0.6,
          getLineColor: [55, 65, 80, 200],
          lineWidthMinPixels: 1,
          getFillColor: (f: any) => metricColor(m, f.properties._v, aMax),
          updateTriggers: { getFillColor: [m, state.adminLevel, aMax, sources.join()] },
          onHover: (info: any) =>
            info.object
              ? showTip(info.x, info.y, adminTip(info.object.properties.unit_id, info.object.properties.unit_name))
              : hideTip(),
        }),
      );
    }
  }

  // h3: ONE layer, each cell coloured by the MAX metric value across selected sources.
  if (state.show.h3 && sources.length) {
    const byCell = new Map<string, any>();
    for (const s of sources) {
      for (const r of h3Cache.get(s) ?? []) {
        if (!hasCov(r)) continue;
        const v = metricValue(r, m);
        const cur = byCell.get(r.h3);
        if (!cur || (v != null && (cur._v == null || v > cur._v)))
          byCell.set(r.h3, { ...r, _v: v, _src: s });
      }
    }
    const rows = [...byCell.values()];
    if (rows.length)
      layers.push(
        new H3HexagonLayer({
          id: "h3-combined",
          data: rows,
          pickable: true,
          extruded: false,
          opacity: 0.6,
          getHexagon: (d: any) => d.h3,
          getFillColor: (d: any) => metricColor(m, d._v, hMax),
          updateTriggers: { getFillColor: [m, hMax, sources.join()] },
          onHover: (info: any) =>
            info.object
              ? showTip(
                  info.x,
                  info.y,
                  tip(`${SOURCE_LABEL[info.object._src] ?? info.object._src} · highest here`, info.object),
                )
              : hideTip(),
        }),
      );
  }

  // agreement view: one combined layer — faint single-source context, bold overlap on top
  if (state.show.buildings && state.view === "agreement" && agreementData) {
    const overlap = new Set(["both", "ms_only", "cems_only", "agree_none"]);
    layers.push(
      new ScatterplotLayer({
        id: "agree-context",
        data: agreementData.filter((d: any) => !overlap.has(d.agreement)),
        getPosition: (d: any) => [d.lon, d.lat],
        getRadius: 5,
        radiusMinPixels: 0.5,
        radiusMaxPixels: 3,
        getFillColor: (d: any) => agreementColor(d.agreement),
      }),
      new ScatterplotLayer({
        id: "agree-overlap",
        data: agreementData.filter((d: any) => overlap.has(d.agreement)),
        getPosition: (d: any) => [d.lon, d.lat],
        getRadius: 9,
        radiusMinPixels: 1.6,
        radiusMaxPixels: 6,
        pickable: true,
        getFillColor: (d: any) => agreementColor(d.agreement),
        onHover: (info: any) =>
          info.object
            ? showTip(info.x, info.y, AGREEMENT[info.object.agreement]?.label ?? info.object.agreement)
            : hideTip(),
      }),
    );
  }

  // building-level (Overture points or native geometry), per source
  for (const s of state.view === "agreement" || !state.show.buildings ? [] : sources) {
    if (state.view === "overture") {
      if (OVERTURE_SERVING === "pmtiles") continue; // served by the buildings PMTiles layers
      const pts = buildingsCache.get(s);
      if (!pts) continue;
      layers.push(
        new ScatterplotLayer({
          id: `bld-exposed-${s}`,
          data: pts.filter((d: any) => !d.damaged),
          getPosition: (d: any) => [d.lon, d.lat],
          getRadius: 5,
          radiusMinPixels: 0.6,
          radiusMaxPixels: 3,
          getFillColor: [110, 118, 130, 85],
        }),
        new ScatterplotLayer({
          id: `bld-damaged-${s}`,
          data: pts.filter((d: any) => d.damaged),
          getPosition: (d: any) => [d.lon, d.lat],
          getRadius: 9,
          radiusMinPixels: 1.6,
          radiusMaxPixels: 6,
          getFillColor: [230, 20, 20, 240],
        }),
      );
    } else {
      if (usePmtiles(s)) continue; // served by its MapLibre PMTiles layer, not deck.gl
      const nat = nativeCache.get(s);
      if (!nat) continue;
      layers.push(
        new GeoJsonLayer({
          id: `native-${s}`,
          data: nat,
          pickable: true,
          filled: true,
          stroked: false,
          // HOTOSM fAIr native geometry is points (not polygons): render them as
          // visible circles. These point props are ignored for polygon sources.
          pointType: "circle",
          getPointRadius: 9,
          pointRadiusUnits: "meters",
          pointRadiusMinPixels: 3.5,
          pointRadiusMaxPixels: 8,
          getFillColor: (f: any) => nativeColor(s, f.properties),
          onHover: (info: any) =>
            info.object
              ? showTip(
                  info.x,
                  info.y,
                  s === "microsoft"
                    ? `Microsoft footprint<br>damaged: ${info.object.properties.damaged ? "yes" : "no"}`
                    : `${SOURCE_LABEL[s] ?? s}<br>grade: ${info.object.properties.ems_grade}` +
                        (info.object.properties.layer_type
                          ? `<br>${info.object.properties.layer_type === "area" ? "coarse block (early estimate)" : "per-building point"}`
                          : "") +
                        (info.object.properties.confidence != null
                          ? `<br>confidence: ${(info.object.properties.confidence * 100).toFixed(0)}%`
                          : ""),
                )
              : hideTip(),
        }),
      );
    }
  }

  // coverage extent: real analysed area per AOI/product (hover = metadata),
  // plus CEMS not-analysed (cloud) gaps — both are coverage, not buildings.
  if (state.show.extent) {
    for (const s of sources) {
      const ext = extentCache.get(s);
      if (!ext) continue;
      const c = SOURCE_COLOR[s] ?? [80, 80, 80];
      layers.push(
        new GeoJsonLayer({
          id: `extent-${s}`,
          data: ext,
          // Outline only: a filled AOI (even at ~5% alpha) is pickable across its
          // whole interior and intercepts hover from the admin units beneath it.
          // The stroke stays pickable, so the coverage tooltip shows near the edge.
          filled: false,
          stroked: true,
          pickable: true,
          getLineColor: [...c, 235] as any,
          lineWidthMinPixels: 2,
          onHover: (info: any) =>
            info.object ? showTip(info.x, info.y, extentTip(s, info.object.properties)) : hideTip(),
        }),
      );
    }
    if (sources.includes("copernicus_ems") && coverageDetailData) {
      layers.push(
        new GeoJsonLayer({
          id: "cems-not-analysed",
          data: {
            type: "FeatureCollection",
            features: coverageDetailData.features.filter(
              (f: any) => f.properties.kind === "not_analysed",
            ),
          } as any,
          filled: true,
          stroked: true,
          pickable: true,
          getFillColor: [95, 100, 110, 110],
          getLineColor: [95, 100, 110, 160],
          getLineWidth: 1,
          lineWidthUnits: "pixels",
          onHover: (info: any) =>
            info.object
              ? showTip(
                  info.x,
                  info.y,
                  `Not analysed — cloud / no imagery<br>${info.object.properties.aoi_name ?? ""} · ${info.object.properties.product ?? ""}`,
                )
              : hideTip(),
        }),
      );
    }
  }

  overlay.setProps({ layers });
  syncPmtiles();
  syncBuildings();
  syncAdmin();
  syncUsgs();
}

function renderLegend() {
  const lg = document.getElementById("legend")!;
  if (state.view === "agreement" && agreementData) {
    const c: Record<string, number> = {};
    for (const p of agreementData) c[p.agreement] = (c[p.agreement] ?? 0) + 1;
    const rows = ["both", "ms_only", "cems_only", "agree_none"]
      .map((k) => {
        const o = AGREEMENT[k];
        return `<div class="key"><span class="swatch" style="background:rgb(${o.color.join(",")})"></span>${o.label} <b>${(c[k] ?? 0).toLocaleString()}</b></div>`;
      })
      .join("");
    lg.innerHTML =
      `<div class="title">Source agreement · overlap buildings</div>${rows}` +
      `<div class="ticks">faint dots = only one source assessed</div>`;
    return;
  }
  const meta = METRICS.find((x) => x.key === state.metric);
  const title = `<div class="title">Aggregation · ${meta?.label ?? state.metric}</div>`;
  const swatch = (c: RGBA) => `<span class="lg-swatch" style="background:rgb(${c[0]},${c[1]},${c[2]})"></span>`;
  // Each bin's swatch is sampled from the SAME colour function the map uses (at a
  // representative value), so the legend always matches what's drawn.
  const binRows = (m: string, bins: { label: string; v: number }[]) =>
    bins.map((b) => `<div class="lg-row">${swatch(metricColor(m, b.v, 1))}${b.label}</div>`).join("");

  // Damage fraction is a true 0–100% rate → fixed classification bands.
  if (state.metric.startsWith("damage_rate")) {
    lg.innerHTML =
      title +
      binRows(state.metric, [
        { label: "No damage detected (0%)", v: 0 },
        { label: "Low (0–10%)", v: 0.05 },
        { label: "Medium (10–25%)", v: 0.175 },
        { label: "High (25–50%)", v: 0.375 },
        { label: "Severe (50%+)", v: 0.75 },
      ]);
    return;
  }
  // Coverage is also 0–100%, but the ramp is inverted (gaps highlighted).
  if (state.metric === "coverage_fraction") {
    lg.innerHTML =
      title +
      binRows("coverage_fraction", [
        { label: "Full (100%)", v: 1 },
        { label: "High (75–100%)", v: 0.875 },
        { label: "Partial (50–75%)", v: 0.625 },
        { label: "Low (25–50%)", v: 0.375 },
        { label: "Minimal (0–25%)", v: 0.125 },
      ]);
    return;
  }
  // Building counts have no fixed scale: keep a graduated strip, but put the real
  // max (highest unit currently in view) on the axis instead of a vague "high".
  const max = legendMax(state.metric);
  const stops = [0, 0.25, 0.5, 0.75, 1].map((t) => metricColor(state.metric, t * max, max));
  lg.innerHTML =
    title +
    `<div class="lg-bins">${stops.map(swatch).join("")}</div>` +
    `<div class="ticks"><span>0</span><span>${num(max)}</span></div>`;
}

// Highest metric value among the units currently drawn (admin and/or H3), so the
// count legend's axis reflects the actual data in view.
function legendMax(metric: string): number {
  const props: any[] = [];
  for (const s of state.sources) {
    if (state.show.admin)
      props.push(
        ...(adminCache.get(`${s}:${state.adminLevel}`)?.features ?? [])
          .map((f: any) => f.properties)
          .filter(hasCov),
      );
    if (state.show.h3) props.push(...(h3Cache.get(s) ?? []).filter(hasCov));
  }
  return maxBy(props, (p) => metricValue(p, metric) ?? 0);
}

// --- data --------------------------------------------------------------------
async function ensureAdmin(source: string, level: number) {
  const k = `${source}:${level}`;
  if (!adminCache.has(k))
    adminCache.set(k, await fetch(`/api/common/admin/${level}?source=${source}`).then((r) => r.json()));
}
async function ensureH3(source: string) {
  if (!h3Cache.has(source)) h3Cache.set(source, await fetch(`/api/common/h3?source=${source}`).then((r) => r.json()));
}
async function ensureBuildings(source: string) {
  if (!buildingsCache.has(source))
    buildingsCache.set(source, await fetch(`/api/buildings?source=${source}`).then((r) => r.json()));
}
async function ensureNative(source: string) {
  if (!nativeCache.has(source)) nativeCache.set(source, await fetch(`/api/native?source=${source}`).then((r) => r.json()));
}
async function ensureExtent(source: string) {
  if (!extentCache.has(source)) extentCache.set(source, await fetch(`/api/extent?source=${source}`).then((r) => r.json()));
}
async function ensureCoverageDetail() {
  if (!coverageDetailData) coverageDetailData = await fetch("/api/coverage_detail").then((r) => r.json());
}
async function ensureAgreement() {
  if (!agreementData) agreementData = await fetch("/api/agreement").then((r) => r.json());
}

async function refresh() {
  const status = document.getElementById("status")!;
  try {
    const tasks: Promise<any>[] = [];
    for (const s of state.sources) {
      if (state.show.admin && ADMIN_SERVING !== "pmtiles") tasks.push(ensureAdmin(s, state.adminLevel));
      if (state.show.h3) tasks.push(ensureH3(s));
      if (state.show.buildings && state.view === "overture" && OVERTURE_SERVING !== "pmtiles")
        tasks.push(ensureBuildings(s));
      if (state.show.buildings && state.view === "native" && !usePmtiles(s))
        tasks.push(ensureNative(s));
      if (state.show.extent) tasks.push(ensureExtent(s));
      if (state.show.extent && s === "copernicus_ems") tasks.push(ensureCoverageDetail());
    }
    if (state.show.buildings && state.view === "agreement") tasks.push(ensureAgreement());

    const total = tasks.length;
    let done = 0;
    const tick = () => {
      const pct = total ? (done / total) * 100 : 100;
      status.innerHTML =
        `<div class="load-row"><span>Loading…</span><span>${done}/${total}</span></div>` +
        `<div class="pbar"><div class="pfill" style="width:${pct}%"></div></div>`;
    };
    if (total) tick();
    await Promise.all(
      tasks.map((t) =>
        t.then((r) => {
          done++;
          if (total) tick();
          return r;
        }),
      ),
    );
    buildLayers();
    renderLegend();
    const srcs = [...state.sources].map((s) => SOURCE_LABEL[s] ?? s).join(" + ") || "none";
    status.textContent = `${srcs} · ${state.view} · adm${state.adminLevel}`;
  } catch (e) {
    status.textContent = `Failed to load: ${e}`;
  }
}

// --- init + wiring -----------------------------------------------------------
const el = (id: string) => document.getElementById(id)!;

async function init() {
  // PMTiles/hyparquet setup is additive — a failure must never blank the app.
  for (const [name, fn] of [
    ["pmtiles", setupPmtiles],
    ["buildings", setupBuildings],
    ["admin", setupAdmin],
    ["usgs", setupUsgs],
  ] as const) {
    try {
      await fn();
    } catch (e) {
      console.error(`v2 ${name} setup failed:`, e);
    }
  }
  const meta = await fetch("/api/sources").then((r) => r.json());
  const sources: string[] = meta.sources;
  METRICS = [
    { key: "damage_rate_detected", label: "Damage fraction" },
    { key: "coverage_fraction", label: "Coverage" },
    { key: "damaged_detected", label: "Damaged buildings" },
  ];
  state.sources = new Set(sources);

  el("sources").innerHTML = sources
    .map((s) => {
      const c = SOURCE_COLOR[s] ?? [120, 120, 120];
      return `<label><input type="checkbox" data-source="${s}" checked /><span class="swatch" style="background:rgb(${c.join(",")})"></span> ${SOURCE_LABEL[s] ?? s}</label>`;
    })
    .join("");
  (el("metric") as HTMLSelectElement).innerHTML = METRICS.map((x) => `<option value="${x.key}">${x.label}</option>`).join("");
  state.metric = "damage_rate_detected";
  (el("metric") as HTMLSelectElement).value = state.metric;

  el("sources")
    .querySelectorAll<HTMLInputElement>("input[data-source]")
    .forEach((box) =>
      box.addEventListener("change", async () => {
        if (box.checked) state.sources.add(box.dataset.source!);
        else state.sources.delete(box.dataset.source!);
        await refresh();
      }),
    );

  await refresh();
}

(el("metric") as HTMLSelectElement).addEventListener("change", () => {
  state.metric = (el("metric") as HTMLSelectElement).value;
  buildLayers();
  renderLegend();
});
(el("view") as HTMLSelectElement).addEventListener("change", async () => {
  state.view = (el("view") as HTMLSelectElement).value;
  await refresh();
});
(el("adminLevel") as HTMLSelectElement).addEventListener("change", async () => {
  state.adminLevel = Number((el("adminLevel") as HTMLSelectElement).value);
  await refresh();
});
// The admin-level and building-source selects are nested under their parent
// toggles; greying them out when the parent is off mirrors that hierarchy.
function syncSubControls() {
  (el("adminLevel") as HTMLSelectElement).disabled = !state.show.admin;
  (el("view") as HTMLSelectElement).disabled = !state.show.buildings;
}
syncSubControls();

document.querySelectorAll<HTMLInputElement>("input[data-layer]").forEach((box) =>
  box.addEventListener("change", async () => {
    state.show[box.dataset.layer!] = box.checked;
    syncSubControls();
    await refresh();
  }),
);

map.on("load", init);

// --- methodology slide-over: glass panel of how the map is built + per-source cards ---
const METHODS_SOURCES: { key: string; tag: string; blurb: string; note: string }[] = [
  {
    key: "copernicus_ems",
    tag: "Reference · expert-mapped",
    blurb:
      "Copernicus Emergency Management Service rapid mapping. Trained analysts grade individual buildings from very-high-resolution satellite imagery.",
    note: "Most authoritative, but only where an activation was mapped.",
  },
  {
    key: "impact_initiatives",
    tag: "Screening · radar",
    blurb:
      "A Sentinel-1 SAR damage proxy. A post-event change in radar backscatter intensity (amplitude, not coherence) flags likely damage over a wide area.",
    note: "A wide-area screen, not confirmed damage.",
  },
  {
    key: "microsoft",
    tag: "AI · per-building",
    blurb:
      "Machine-learning damage labels on Microsoft's global building footprints, classifying each footprint from post-event imagery.",
    note: "Dense automated coverage where imagery allows.",
  },
  {
    key: "osu",
    tag: "Research · radar",
    blurb:
      "Oregon State University Sentinel-1 coherence analysis. Loss of radar coherence indicates damage.",
    note: "An independent radar signal alongside the SAR proxy.",
  },
  {
    key: "hot_osm",
    tag: "Community · ML",
    blurb:
      "The Humanitarian OpenStreetMap Team's fAIr model detects damaged buildings from imagery, aligned to the OpenStreetMap community base.",
    note: "Open, community-driven detection.",
  },
  {
    key: "disha",
    tag: "AI · zero-shot",
    blurb:
      "DISHA (UN Global Pulse) runs Google Earth AI's zero-shot damage model on pre/post imagery over NW Caracas, on Google Open Buildings footprints.",
    note: "Preview over a small AOI; provider validation pending.",
  },
];

function renderMethodsCards() {
  const host = document.getElementById("methods-cards");
  if (!host) return;
  host.innerHTML = METHODS_SOURCES.map((m, i) => {
    const c = SOURCE_COLOR[m.key] ?? [120, 120, 120];
    return (
      `<article class="source-card" style="--accent:rgb(${c.join(",")});animation-delay:${i * 65}ms">` +
      `<div class="card-glow"></div>` +
      `<div class="card-top"><span class="card-dot"></span><h3>${SOURCE_LABEL[m.key] ?? m.key}</h3></div>` +
      `<span class="card-chip">${m.tag}</span>` +
      `<p class="card-blurb">${m.blurb}</p>` +
      `<p class="card-note">${m.note}</p>` +
      `</article>`
    );
  }).join("");
}

const methodsEl = document.getElementById("methods");
const openMethods = () => {
  renderMethodsCards();
  methodsEl?.removeAttribute("hidden");
};
const closeMethods = () => methodsEl?.setAttribute("hidden", "");
document.getElementById("methods-open")?.addEventListener("click", openMethods);
document.getElementById("methods-close")?.addEventListener("click", closeMethods);
methodsEl?.querySelector(".methods-bg")?.addEventListener("click", closeMethods);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && methodsEl && !methodsEl.hasAttribute("hidden")) closeMethods();
});

// Panel "?" affordances (next to Sources / Colour aggregation) open the note.
document.querySelectorAll(".help").forEach((el) => {
  el.addEventListener("click", openMethods);
  el.addEventListener("keydown", (e) => {
    const k = (e as KeyboardEvent).key;
    if (k === "Enter" || k === " ") {
      e.preventDefault();
      openMethods();
    }
  });
});
