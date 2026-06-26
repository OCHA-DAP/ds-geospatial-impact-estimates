import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";
import maplibregl from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer } from "@deck.gl/layers";
import { H3HexagonLayer } from "@deck.gl/geo-layers";

type Metric = "damaged_fraction" | "buildings_damaged" | "buildings_total";
type RGBA = [number, number, number, number];

const state = {
  metric: "damaged_fraction" as Metric,
  show: { adm3: true, h3: true, footprints: false },
};

let adm3: any = null;
let h3: any[] = [];
let footprints: any = null;

const map = new maplibregl.Map({
  container: "map",
  style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  center: [-67.03, 10.59],
  zoom: 12,
});
const overlay = new MapboxOverlay({ interleaved: false, layers: [] });
map.addControl(overlay as any);

// --- colour helpers: sequential yellow -> dark red; null -> faint grey -------
function damageColor(frac: number | null | undefined): RGBA {
  if (frac == null || Number.isNaN(frac)) return [200, 200, 200, 35];
  const f = Math.max(0, Math.min(1, frac));
  return [240, Math.round(220 * (1 - f)), Math.round(40 * (1 - f)), 205];
}
function maxOf(rows: any[], key: string, read: (r: any) => number): number {
  return Math.max(1, ...rows.map(read).filter((v) => !Number.isNaN(v)));
}

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

const num = (n: any) =>
  n == null || Number.isNaN(n) ? "—" : Math.round(n).toLocaleString();
const pct = (n: any) =>
  n == null || Number.isNaN(n) ? "—" : `${(100 * n).toFixed(1)}%`;

// --- layers ------------------------------------------------------------------
function buildLayers() {
  const layers: any[] = [];

  if (state.show.adm3 && adm3) {
    layers.push(
      new GeoJsonLayer({
        id: "adm3",
        data: adm3,
        pickable: true,
        filled: true,
        stroked: true,
        opacity: 0.4,
        getLineColor: [55, 65, 80, 200],
        lineWidthMinPixels: 1,
        getFillColor: (f: any) => damageColor(f.properties.damaged_fraction),
        updateTriggers: { getFillColor: [state.metric] },
        onHover: (info: any) =>
          info.object
            ? showTip(
                info.x,
                info.y,
                `<b>${info.object.properties.unit_name}</b><br>` +
                  `buildings: ${num(info.object.properties.buildings_total)}<br>` +
                  `damaged: ${num(info.object.properties.buildings_damaged)} ` +
                  `(${pct(info.object.properties.damaged_fraction)})`,
              )
            : hideTip(),
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
          f.properties.damaged ? [232, 36, 36, 190] : [90, 130, 200, 70],
        onHover: (info: any) =>
          info.object
            ? showTip(
                info.x,
                info.y,
                `Building<br>damaged: ${info.object.properties.damaged ? "yes" : "no"}`,
              )
            : hideTip(),
      }),
    );
  }

  if (state.show.h3 && h3.length) {
    const m = state.metric;
    const max = maxOf(h3, m, (d) => d[m] ?? 0);
    layers.push(
      new H3HexagonLayer({
        id: "h3",
        data: h3,
        pickable: true,
        extruded: false,
        opacity: 0.62,
        filled: true,
        stroked: false,
        getHexagon: (d: any) => d.h3,
        getFillColor: (d: any) =>
          m === "damaged_fraction"
            ? damageColor(d.damaged_fraction)
            : damageColor((d[m] ?? 0) / max),
        updateTriggers: { getFillColor: [m] },
        onHover: (info: any) =>
          info.object
            ? showTip(
                info.x,
                info.y,
                `Hex · buildings: ${num(info.object.buildings_total)}<br>` +
                  `damaged: ${num(info.object.buildings_damaged)} ` +
                  `(${pct(info.object.damaged_fraction)})`,
              )
            : hideTip(),
      }),
    );
  }

  overlay.setProps({ layers });
}

// --- legend ------------------------------------------------------------------
function renderLegend() {
  const stops = [0, 0.25, 0.5, 0.75, 1].map(damageColor);
  const grad = `linear-gradient(90deg, ${stops
    .map((c) => `rgb(${c[0]},${c[1]},${c[2]})`)
    .join(",")})`;
  const label =
    state.metric === "damaged_fraction" ? "Damaged fraction" : "Relative intensity";
  document.getElementById("legend")!.innerHTML =
    `<div class="title">${label}</div><div class="bar" style="background:${grad}"></div>` +
    `<div class="ticks"><span>low</span><span>high</span></div>`;
}

// --- data + wiring -----------------------------------------------------------
async function load() {
  const status = document.getElementById("status")!;
  try {
    const [a, hx, fp] = await Promise.all([
      fetch("/api/admin/3").then((r) => r.json()),
      fetch("/api/h3").then((r) => r.json()),
      fetch("/api/footprints").then((r) => r.json()),
    ]);
    adm3 = a;
    h3 = hx;
    footprints = fp;
    status.textContent = `${h3.length} hexes · ${a.features.length} parroquias · ${fp.features.length.toLocaleString()} footprints`;
    buildLayers();
    renderLegend();
  } catch (e) {
    status.textContent = `Failed to load: ${e}`;
  }
}

document.querySelectorAll<HTMLInputElement>("input[data-layer]").forEach((el) =>
  el.addEventListener("change", () => {
    (state.show as any)[el.dataset.layer!] = el.checked;
    buildLayers();
  }),
);
document.querySelectorAll<HTMLInputElement>('input[name="metric"]').forEach((el) =>
  el.addEventListener("change", () => {
    if (el.checked) {
      state.metric = el.value as Metric;
      buildLayers();
      renderLegend();
    }
  }),
);

map.on("load", load);
