import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";
import maplibregl from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";
import { H3HexagonLayer } from "@deck.gl/geo-layers";

type RGBA = [number, number, number, number];

const SOURCE_LABEL: Record<string, string> = {
  microsoft: "Microsoft",
  copernicus_ems: "Copernicus EMS",
};
const SOURCE_COLOR: Record<string, [number, number, number]> = {
  microsoft: [40, 110, 205],
  copernicus_ems: [235, 125, 20],
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

const map = new maplibregl.Map({
  container: "map",
  style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  center: [-67.03, 10.59],
  zoom: 11,
});
const overlay = new MapboxOverlay({ interleaved: false, layers: [] });
map.addControl(overlay as any);

// --- colour ------------------------------------------------------------------
function damageColor(t: number | null | undefined): RGBA {
  if (t == null || Number.isNaN(t)) return [200, 200, 200, 35];
  const f = Math.max(0, Math.min(1, t));
  return [240, Math.round(220 * (1 - f)), Math.round(40 * (1 - f)), 205];
}
function metricValue(p: any, metric: string): number | null {
  if (metric === "damage_rate_detected")
    return p.exposed_buildings ? p.damaged_detected / p.exposed_buildings : null;
  if (metric === "damage_rate_extrapolated")
    return p.exposed_buildings ? (p.damaged_extrapolated ?? 0) / p.exposed_buildings : null;
  return p[metric];
}
function metricColor(metric: string, value: number | null | undefined, max: number): RGBA {
  if (value == null || Number.isNaN(value)) return [200, 200, 200, 35];
  if (metric === "coverage_fraction") return damageColor(1 - Math.max(0, Math.min(1, value)));
  if (metric.startsWith("damage_rate")) return damageColor(Math.max(0, Math.min(1, value)));
  return damageColor(max ? value / max : 0);
}
function nativeColor(source: string, p: any): RGBA {
  if (source === "microsoft") return p.damaged ? [220, 30, 30, 205] : [120, 128, 140, 70];
  const cls = p.damage_class; // CEMS: 1 possibly .. 3 destroyed
  return cls == null ? [225, 60, 40, 200] : damageColor(Math.max(0.25, cls / 3));
}
const maxBy = (arr: any[], get: (x: any) => number) =>
  Math.max(1, ...arr.map(get).filter((v) => !Number.isNaN(v)));
const hasCov = (p: any) => (p?.coverage_fraction ?? 0) > 0;

// --- tooltip -----------------------------------------------------------------
const tooltip = document.getElementById("tooltip")!;
function showTip(x: number, y: number, html: string) {
  tooltip.style.display = "block";
  tooltip.style.left = `${x + 14}px`;
  tooltip.style.top = `${y + 14}px`;
  tooltip.innerHTML = html;
}
const hideTip = () => {
  tooltip.style.display = "none";
};
const num = (n: any) => (n == null || Number.isNaN(n) ? "—" : Math.round(n).toLocaleString());
const pct = (n: any) => (n == null || Number.isNaN(n) ? "—" : `${(100 * n).toFixed(0)}%`);
const tip = (name: string, p: any) =>
  `<b>${name}</b><br>total buildings: ${num(p.exposed_buildings)}<br>coverage: ${pct(p.coverage_fraction)}<br>` +
  `damaged: ${num(p.damaged_detected)}<br>damaged (est.): ${num(p.damaged_extrapolated)}`;

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

  // admin aggregation (common model, shared by both views)
  for (const s of sources) {
    if (!state.show.admin) break;
    const data = adminCache.get(`${s}:${state.adminLevel}`);
    if (!data) continue;
    layers.push(
      new GeoJsonLayer({
        id: `admin-${s}-${state.adminLevel}`,
        data: { type: "FeatureCollection", features: data.features.filter((f: any) => hasCov(f.properties)) },
        pickable: true,
        filled: true,
        stroked: true,
        opacity: 0.6,
        getLineColor: [55, 65, 80, 200],
        lineWidthMinPixels: 1,
        getFillColor: (f: any) => metricColor(m, metricValue(f.properties, m), aMax),
        updateTriggers: { getFillColor: [m, state.adminLevel, aMax] },
        onHover: (info: any) =>
          info.object
            ? showTip(info.x, info.y, tip(`${info.object.properties.unit_name} · ${SOURCE_LABEL[s] ?? s}`, info.object.properties))
            : hideTip(),
      }),
    );
  }

  // h3 (common)
  for (const s of sources) {
    if (!state.show.h3) break;
    const rows = (h3Cache.get(s) ?? []).filter(hasCov);
    if (!rows.length) continue;
    layers.push(
      new H3HexagonLayer({
        id: `h3-${s}`,
        data: rows,
        pickable: true,
        extruded: false,
        opacity: 0.6,
        getHexagon: (d: any) => d.h3,
        getFillColor: (d: any) => metricColor(m, metricValue(d, m), hMax),
        updateTriggers: { getFillColor: [m, hMax] },
        onHover: (info: any) =>
          info.object ? showTip(info.x, info.y, tip(SOURCE_LABEL[s] ?? s, info.object)) : hideTip(),
      }),
    );
  }

  // building-level: Overture points OR native geometry
  for (const s of sources) {
    if (!state.show.buildings) break;
    if (state.view === "overture") {
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
      const nat = nativeCache.get(s);
      if (!nat) continue;
      layers.push(
        new GeoJsonLayer({
          id: `native-${s}`,
          data: nat,
          pickable: true,
          filled: true,
          stroked: false,
          getFillColor: (f: any) => nativeColor(s, f.properties),
          onHover: (info: any) =>
            info.object
              ? showTip(
                  info.x,
                  info.y,
                  s === "microsoft"
                    ? `Microsoft footprint<br>damaged: ${info.object.properties.damaged ? "yes" : "no"}`
                    : `Copernicus EMS<br>grade: ${info.object.properties.ems_grade}`,
                )
              : hideTip(),
        }),
      );
    }
  }

  // source coverage extent (AOI bbox / convex hull), labelled by source colour
  for (const s of sources) {
    if (!state.show.extent) break;
    const ext = extentCache.get(s);
    if (!ext) continue;
    const c = SOURCE_COLOR[s] ?? [80, 80, 80];
    layers.push(
      new GeoJsonLayer({
        id: `extent-${s}`,
        data: ext,
        filled: true,
        stroked: true,
        getFillColor: [...c, 12] as any,
        getLineColor: [...c, 235] as any,
        lineWidthMinPixels: 2,
      }),
    );
  }

  overlay.setProps({ layers });
}

function renderLegend() {
  const meta = METRICS.find((x) => x.key === state.metric);
  const stops = [0, 0.25, 0.5, 0.75, 1].map(damageColor);
  const grad = `linear-gradient(90deg, ${stops.map((c) => `rgb(${c[0]},${c[1]},${c[2]})`).join(",")})`;
  const [lo, hi] = state.metric === "coverage_fraction" ? ["full", "partial"] : ["low", "high"];
  document.getElementById("legend")!.innerHTML =
    `<div class="title">Aggregation · ${meta?.label ?? state.metric}</div>` +
    `<div class="bar" style="background:${grad}"></div>` +
    `<div class="ticks"><span>${lo}</span><span>${hi}</span></div>`;
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

async function refresh() {
  const status = document.getElementById("status")!;
  status.textContent = "Loading…";
  try {
    const tasks: Promise<any>[] = [];
    for (const s of state.sources) {
      if (state.show.admin) tasks.push(ensureAdmin(s, state.adminLevel));
      if (state.show.h3) tasks.push(ensureH3(s));
      if (state.show.buildings) tasks.push(state.view === "overture" ? ensureBuildings(s) : ensureNative(s));
      if (state.show.extent) tasks.push(ensureExtent(s));
    }
    await Promise.all(tasks);
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
  const meta = await fetch("/api/sources").then((r) => r.json());
  const sources: string[] = meta.sources;
  METRICS = [
    { key: "damage_rate_detected", label: "Damage rate (detected)" },
    { key: "damage_rate_extrapolated", label: "Damage rate (estimated)" },
    ...meta.metrics,
  ];
  state.sources = new Set(sources);

  el("sources").innerHTML = sources
    .map((s) => {
      const c = SOURCE_COLOR[s] ?? [120, 120, 120];
      return `<label><span class="swatch" style="background:rgb(${c.join(",")})"></span><input type="checkbox" data-source="${s}" checked /> ${SOURCE_LABEL[s] ?? s}</label>`;
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
document.querySelectorAll<HTMLInputElement>("input[data-layer]").forEach((box) =>
  box.addEventListener("change", async () => {
    state.show[box.dataset.layer!] = box.checked;
    await refresh();
  }),
);

map.on("load", init);
