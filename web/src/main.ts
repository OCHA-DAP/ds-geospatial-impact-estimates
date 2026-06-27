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
  `analysed: ${num(p.analysed_buildings)}<br>` +
  `damaged: ${num(p.damaged_detected)}<br>` +
  `damage fraction: ${pct(p.analysed_buildings ? p.damaged_detected / p.analysed_buildings : null)}<br>` +
  `damaged (est. full unit): ${num(p.damaged_extrapolated)}`;

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
          filled: true,
          stroked: true,
          pickable: true,
          getFillColor: [...c, 12] as any,
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
  const stops = [0, 0.15, 0.35, 0.6, 1].map((t) => damageColor(lift(t)));
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
async function ensureCoverageDetail() {
  if (!coverageDetailData) coverageDetailData = await fetch("/api/coverage_detail").then((r) => r.json());
}
async function ensureAgreement() {
  if (!agreementData) agreementData = await fetch("/api/agreement").then((r) => r.json());
}

async function refresh() {
  const status = document.getElementById("status")!;
  status.textContent = "Loading…";
  try {
    const tasks: Promise<any>[] = [];
    for (const s of state.sources) {
      if (state.show.admin) tasks.push(ensureAdmin(s, state.adminLevel));
      if (state.show.h3) tasks.push(ensureH3(s));
      if (state.show.buildings && state.view === "overture") tasks.push(ensureBuildings(s));
      if (state.show.buildings && state.view === "native") tasks.push(ensureNative(s));
      if (state.show.extent) tasks.push(ensureExtent(s));
      if (state.show.extent && s === "copernicus_ems") tasks.push(ensureCoverageDetail());
    }
    if (state.show.buildings && state.view === "agreement") tasks.push(ensureAgreement());
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
    { key: "damage_rate_detected", label: "Damage fraction" },
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
