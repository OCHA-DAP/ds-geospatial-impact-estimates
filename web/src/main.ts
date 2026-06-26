import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";
import maplibregl from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer } from "@deck.gl/layers";
import { H3HexagonLayer } from "@deck.gl/geo-layers";

type RGBA = [number, number, number, number];

const state = {
  source: "microsoft",
  metric: "damaged_detected",
  adminLevel: 3,
  show: { admin: true, h3: false, footprints: false },
};

let SOURCES: string[] = [];
let METRICS: { key: string; label: string }[] = [];
const adminCache = new Map<string, any>(); // `${source}:${level}` -> GeoJSON
const h3Cache = new Map<string, any[]>(); // source -> rows
let footprints: any = null;

const map = new maplibregl.Map({
  container: "map",
  style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  center: [-67.03, 10.59],
  zoom: 11,
});
const overlay = new MapboxOverlay({ interleaved: false, layers: [] });
map.addControl(overlay as any);

// --- colour: sequential yellow -> dark red; null -> faint grey ---------------
function damageColor(t: number | null | undefined): RGBA {
  if (t == null || Number.isNaN(t)) return [200, 200, 200, 35];
  const f = Math.max(0, Math.min(1, t));
  return [240, Math.round(220 * (1 - f)), Math.round(40 * (1 - f)), 205];
}
function metricColor(metric: string, value: number | null | undefined, max: number): RGBA {
  if (value == null || Number.isNaN(value)) return [200, 200, 200, 35];
  // coverage: highlight INCOMPLETE coverage (partial glows red, full fades)
  if (metric === "coverage_fraction") return damageColor(1 - Math.max(0, Math.min(1, value)));
  return damageColor(max ? value / max : 0);
}
const maxBy = (arr: any[], get: (x: any) => number) =>
  Math.max(1, ...arr.map(get).filter((v) => !Number.isNaN(v)));

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

function tip(name: string | null, p: any): string {
  return (
    (name ? `<b>${name}</b><br>` : "") +
    `exposed: ${num(p.exposed_buildings)}<br>` +
    `coverage: ${pct(p.coverage_fraction)}<br>` +
    `damaged (detected): ${num(p.damaged_detected)}<br>` +
    `damaged (extrapolated): ${num(p.damaged_extrapolated)}`
  );
}

// --- layers ------------------------------------------------------------------
function buildLayers() {
  const m = state.metric;
  const layers: any[] = [];

  const admin = adminCache.get(`${state.source}:${state.adminLevel}`);
  if (state.show.admin && admin) {
    const amax = maxBy(admin.features, (f) => f.properties[m] ?? 0);
    layers.push(
      new GeoJsonLayer({
        id: `admin-${state.source}-${state.adminLevel}`,
        data: admin,
        pickable: true,
        filled: true,
        stroked: true,
        opacity: 0.6,
        getLineColor: [55, 65, 80, 200],
        lineWidthMinPixels: 1,
        getFillColor: (f: any) => metricColor(m, f.properties[m], amax),
        updateTriggers: { getFillColor: [m, state.source, state.adminLevel] },
        onHover: (info: any) =>
          info.object
            ? showTip(info.x, info.y, tip(info.object.properties.unit_name, info.object.properties))
            : hideTip(),
      }),
    );
  }

  const h3 = h3Cache.get(state.source);
  if (state.show.h3 && h3) {
    const hmax = maxBy(h3, (d) => d[m] ?? 0);
    layers.push(
      new H3HexagonLayer({
        id: `h3-${state.source}`,
        data: h3,
        pickable: true,
        extruded: false,
        opacity: 0.62,
        filled: true,
        stroked: false,
        getHexagon: (d: any) => d.h3,
        getFillColor: (d: any) => metricColor(m, d[m], hmax),
        updateTriggers: { getFillColor: [m, state.source] },
        onHover: (info: any) =>
          info.object ? showTip(info.x, info.y, tip(null, info.object)) : hideTip(),
      }),
    );
  }

  if (state.show.footprints && footprints) {
    layers.push(
      new GeoJsonLayer({
        id: "footprints",
        data: footprints,
        pickable: true,
        filled: true,
        stroked: false,
        getFillColor: (f: any) =>
          f.properties.damaged ? [200, 30, 30, 235] : [20, 20, 20, 210],
        onHover: (info: any) =>
          info.object
            ? showTip(info.x, info.y, `Building<br>damaged: ${info.object.properties.damaged ? "yes" : "no"}`)
            : hideTip(),
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
    `<div class="title">${meta?.label ?? state.metric}</div>` +
    `<div class="bar" style="background:${grad}"></div>` +
    `<div class="ticks"><span>${lo}</span><span>${hi}</span></div>`;
}

// --- data --------------------------------------------------------------------
async function ensureAdmin(source: string, level: number) {
  const k = `${source}:${level}`;
  if (!adminCache.has(k)) {
    adminCache.set(k, await fetch(`/api/common/admin/${level}?source=${source}`).then((r) => r.json()));
  }
  return adminCache.get(k);
}
async function ensureH3(source: string) {
  if (!h3Cache.has(source)) {
    h3Cache.set(source, await fetch(`/api/common/h3?source=${source}`).then((r) => r.json()));
  }
  return h3Cache.get(source);
}
async function ensureFootprints() {
  if (!footprints) footprints = await fetch("/api/footprints").then((r) => r.json());
  return footprints;
}

async function refresh() {
  const status = document.getElementById("status")!;
  try {
    const tasks: Promise<any>[] = [ensureAdmin(state.source, state.adminLevel)];
    if (state.show.h3) tasks.push(ensureH3(state.source));
    if (state.show.footprints) tasks.push(ensureFootprints());
    await Promise.all(tasks);
    const admin = adminCache.get(`${state.source}:${state.adminLevel}`);
    status.textContent = `${state.source} · adm${state.adminLevel} · ${admin.features.length} units`;
    buildLayers();
  } catch (e) {
    status.textContent = `Failed to load: ${e}`;
  }
}

// --- init + wiring -----------------------------------------------------------
const el = (id: string) => document.getElementById(id) as HTMLSelectElement;

async function init() {
  const meta = await fetch("/api/sources").then((r) => r.json());
  SOURCES = meta.sources;
  METRICS = meta.metrics;
  el("source").innerHTML = SOURCES.map((s) => `<option value="${s}">${s}</option>`).join("");
  el("metric").innerHTML = METRICS.map((m) => `<option value="${m.key}">${m.label}</option>`).join("");
  state.source = SOURCES.includes("microsoft") ? "microsoft" : SOURCES[0];
  state.metric = METRICS[0].key;
  el("source").value = state.source;
  el("metric").value = state.metric;
  await refresh();
  renderLegend();
}

el("source").addEventListener("change", async () => {
  state.source = el("source").value;
  await refresh();
});
el("metric").addEventListener("change", () => {
  state.metric = el("metric").value;
  buildLayers();
  renderLegend();
});
el("adminLevel").addEventListener("change", async () => {
  state.adminLevel = Number(el("adminLevel").value);
  await ensureAdmin(state.source, state.adminLevel);
  buildLayers();
});
document.querySelectorAll<HTMLInputElement>("input[data-layer]").forEach((box) =>
  box.addEventListener("change", async () => {
    (state.show as any)[box.dataset.layer!] = box.checked;
    if (box.checked && box.dataset.layer === "h3") await ensureH3(state.source);
    if (box.checked && box.dataset.layer === "footprints") await ensureFootprints();
    buildLayers();
  }),
);

map.on("load", init);
