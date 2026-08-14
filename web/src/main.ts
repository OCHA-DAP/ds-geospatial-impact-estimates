import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";
import maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import { asyncBufferFromUrl, parquetReadObjects } from "hyparquet";
import { LEGACY_SERVER_EVENT, TOKEN_URL } from "./config";
import { currentEventId, eventDir, fetchEvents, type EventInfo } from "./events";
import { esc, renderBootError, renderEmptyRegistry, renderEventError, renderLanding } from "./landing";

// One token fetch per session, shared by all callers. Four init paths need the
// blob SAS; without memoization each did its own round-trip — same-origin+cached
// on the App Service, but a fresh cross-origin mint each time on the SWA/issuer.
let _tokenPromise: Promise<any> | null = null;
const getToken = () => (_tokenPromise ??= fetch(TOKEN_URL).then((r) => r.json()));

const EVENT_ID = currentEventId(); // null -> landing page; non-null -> event view

// Source display metadata: shared by the event viewer (initViewer) and the
// methodology slide-over, which is not event-scoped (same sources, any event).
const SOURCE_LABEL: Record<string, string> = {
  microsoft: "Microsoft",
  copernicus_ems: "Copernicus EMS",
  impact_initiatives: "IMPACT (SAR)",
  hot_osm: "HotOSM",
  osu: "OSU (SAR)",
  disha: "DISHA",
  unep_debris: "UNEP (SAR)",
  uh: "UH QuakeDamage",
  list: "WFP-LIST-CERN (SAR)",
};
const SOURCE_COLOR: Record<string, [number, number, number]> = {
  microsoft: [40, 110, 205],
  copernicus_ems: [235, 125, 20],
  impact_initiatives: [150, 70, 190],
  hot_osm: [210, 45, 130],
  osu: [20, 160, 130],
  disha: [225, 200, 40],
  unep_debris: [140, 90, 55],
  uh: [110, 190, 70],
  list: [214, 69, 65],
};
// Fixed display order for the source list / legend (Copernicus first, UNEP last).
const SOURCE_ORDER = [
  "copernicus_ems", "microsoft", "disha", "hot_osm", "impact_initiatives", "osu", "unep_debris", "uh", "list",
];
const sourceRank = (s: string) => {
  const i = SOURCE_ORDER.indexOf(s);
  return i < 0 ? 999 : i;
};

// Everything below is event-scoped: the map instance, all layer/source setup,
// panel wiring, and data fetches. It runs ONLY once boot() has confirmed the
// hash names a real registry event — never for the landing or error routes.
// tok is deliberately NOT a parameter here: every fetch below calls the module-
// level memoized getToken() itself (it's a no-op await once resolved), and
// nothing in this function ever read the caller's copy directly.
function initViewer(ev: EventInfo, events: EventInfo[]) {
  // Static meta artifacts (platinum/event=<id>/meta/*, written by build_platinum
  // export_meta). These replace the /api/sources, /api/extent and /api/coverage_detail
  // server routes: constant between data refreshes, so they are read straight from
  // blob like the rest of the platinum tier — the API server is out of the default
  // load path (ADR-0021).
  const fetchMeta = async (name: string) => {
    const tok = await getToken();
    return fetch(`${eventDir(tok, EVENT_ID!)}/meta/${name}?${tok.sas}`).then((r) => r.json());
  };
  // extents.json bundles every source's analysed extent -> one request instead of one per source.
  let _extentsAll: Promise<Record<string, any>> | null = null;
  const getExtents = () => (_extentsAll ??= fetchMeta("extents.json"));
  // Agreement-view legend totals (precomputed in the pipeline — a client can't count
  // buildings in tiles it hasn't rendered).
  let agreementCounts: Record<string, number> | null = null;
  async function ensureAgreementCounts() {
    if (!agreementCounts) agreementCounts = await fetchMeta("agreement_counts.json");
  }

  type RGBA = [number, number, number, number];


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
  const extentCache = new Map<string, any>();
  let coverageDetailData: any = null; // CEMS AOI + not-analysed (cloud) shapes
  // Source-agreement categories (the spatial Venn) — used by the "agreement" view.
  const AGREEMENT: Record<string, { label: string; color: [number, number, number] }> = {
    both: { label: "Both damaged", color: [150, 25, 40] },
    ms_only: { label: "Microsoft only", color: [40, 110, 205] },
    cems_only: { label: "Copernicus only", color: [235, 125, 20] },
    agree_none: { label: "Agree: undamaged", color: [165, 170, 178] },
  };
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
  });

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
    { mode: "pmtiles"; file: string; sourceLayer: string; layers: PmLayer[]; hover: (p: any) => string };

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
    // IMPACT SAR (v2 vector footprints) and OSU (Overture footprints flagged damaged) each have
    // their own polygon footprints, so they serve as native fill tiles like the other sources
    // (retiring the last deck.gl /api/native path). Both are a single damaged class -> orange.
    impact_initiatives: {
      mode: "pmtiles",
      file: "native-impact_initiatives/building_damage.pmtiles",
      sourceLayer: "building_damage",
      layers: [
        {
          id: "pmt-sar",
          spec: { type: "fill", paint: { "fill-color": DAMAGE_BY_CLASS, "fill-opacity": 0.8 } },
        },
      ],
      hover: (p) =>
        `${SOURCE_LABEL["impact_initiatives"] ?? "impact_initiatives"}<br>grade: ${p.ems_grade}` +
        (p.affected_fraction != null ? `<br>affected: ${Math.round(p.affected_fraction * 100)}%` : ""),
    },
    osu: {
      mode: "pmtiles",
      file: "native-osu/damage_footprints.pmtiles",
      sourceLayer: "damage_footprints",
      layers: [
        {
          id: "pmt-osu",
          spec: { type: "fill", paint: { "fill-color": DAMAGE_BY_CLASS, "fill-opacity": 0.8 } },
        },
      ],
      hover: (p) =>
        `${SOURCE_LABEL["osu"] ?? "osu"}<br>grade: ${p.ems_grade}` +
        // v1 carries a categorical confidence tier; v0 a continuous probability. Show
        // whichever the tile has so a version switch needs no frontend rebuild.
        (p.damage_confidence != null
          ? `<br>confidence: ${String(p.damage_confidence).replace(/_/g, " ")}`
          : p.damage_probability != null
            ? `<br>probability: ${Math.round(p.damage_probability * 100)}%`
            : ""),
    },
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
    unep_debris: {
      mode: "pmtiles",
      file: "native-unep_debris/debris.pmtiles",
      sourceLayer: "debris",
      // Polygons coloured by the source's own metric — debris MASS (tonnes) — not a
      // damage grade. Detected-only; native count 96,046 vs 75,477 on the Overture
      // base (ADR-0017).
      layers: [
        {
          id: "pmt-debris",
          spec: {
            type: "fill",
            paint: {
              "fill-color": [
                "interpolate", ["linear"], ["get", "debris_tonnes"],
                10, "rgb(255,224,160)", 100, "rgb(240,140,32)", 1000, "rgb(178,24,24)",
              ],
              "fill-opacity": 0.85,
            },
          },
        },
      ],
      hover: (p) =>
        `${SOURCE_LABEL["unep_debris"] ?? "unep_debris"}<br>debris: ` +
        `${Math.round(p.debris_tonnes).toLocaleString()} t`,
    },
    uh: {
      mode: "pmtiles",
      file: "native-uh/footprints.pmtiles",
      sourceLayer: "footprints",
      // Graded footprints coloured by the source's own three-class grade (intact/
      // damaged/destroyed) — the intact footprints are the analysed denominator. Native
      // 76,378 damaged/destroyed (deduped) vs ~74,700 on the Overture base (ADR-0017/0018).
      // One fill layer PER grade, ordered intact -> damaged -> destroyed. MapLibre draws
      // later layers on top, so where two graded footprints overlap (the source has ~500
      // near-coincident footprints with conflicting grades, plus any dup we didn't dedup),
      // the WORST grade wins visually instead of alpha-blending to brown. Intact stays
      // opaque enough (0.6) that the damage-fraction choropleth beneath can't tint it.
      layers: [
        {
          id: "pmt-uh-intact",
          spec: {
            type: "fill",
            filter: ["==", ["get", "grade"], "intact"],
            paint: { "fill-color": "#8b95a1", "fill-opacity": 0.6 },
          },
        },
        {
          id: "pmt-uh-damaged",
          spec: {
            type: "fill",
            filter: ["==", ["get", "grade"], "damaged"],
            paint: { "fill-color": "rgb(240,124,32)", "fill-opacity": 0.92 },
          },
        },
        {
          id: "pmt-uh-destroyed",
          spec: {
            type: "fill",
            filter: ["==", ["get", "grade"], "destroyed"],
            paint: { "fill-color": "rgb(202,24,24)", "fill-opacity": 0.95 },
          },
        },
      ],
      hover: (p) => `${SOURCE_LABEL["uh"] ?? "uh"}<br>grade: ${p.grade}`,
    },
  };

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
    unep_debris: { seen: "debris_dmg", dmg: "debris_dmg" }, // detected-only (mass source)
    uh: { seen: "uh_dmg", dmg: "uh_dmg" }, // damaged-only in the per-building layer (building_flags
    // carries uh_dmg, not the full uh_analysed set — same size-bound as SAR/OSU). The admin
    // choropleth is still coverage-aware from the gold facts.
    list: { seen: "list_dmg", dmg: "list_dmg" }, // damaged-only (class 2; validated vs IMPACT/OSU)
  };

  // Add the one buildings tile + per-source exposed/damaged circle layers (hidden).
  async function setupBuildings() {
    if (OVERTURE_SERVING !== "pmtiles") return;
    const tok = await getToken();
    const dir = eventDir(tok, EVENT_ID!);
    map.addSource("pmt-src-buildings", {
      type: "vector",
      url: `pmtiles://${dir}/buildings/building_flags.pmtiles?${tok.sas}`,
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

    // Agreement view from the SAME tiles: the MS/CEMS flags are tile properties, so the
    // spatial-Venn category is a paint expression — /api/agreement (deck.gl) retired.
    const b = (f: string) => ["to-boolean", ["get", f]];
    const bothAnalysed = ["all", b("ms_analysed"), b("cems_analysed")];
    const agreeCat = [
      "case",
      ["all", b("ms_dmg"), b("cems_dmg")], "both",
      b("ms_dmg"), "ms_only",
      b("cems_dmg"), "cems_only",
      "agree_none",
    ];
    map.addLayer({
      id: "bpm-agree-context", // single-source areas, faint (matches deck.gl 28/255 alpha)
      source: "pmt-src-buildings",
      "source-layer": "building_flags",
      type: "circle",
      layout: { visibility: "none" },
      filter: ["all", ["any", b("ms_analysed"), b("cems_analysed")], ["!", bothAnalysed as any]],
      paint: {
        "circle-color": ["case", b("ms_analysed"), "rgb(40,110,205)", "rgb(235,125,20)"],
        "circle-opacity": 0.11,
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 0.7, 15, 3],
        "circle-stroke-width": 0,
      },
    } as any);
    map.addLayer({
      id: "bpm-agree-overlap", // both sources assessed: the Venn categories, bold
      source: "pmt-src-buildings",
      "source-layer": "building_flags",
      type: "circle",
      layout: { visibility: "none" },
      filter: bothAnalysed as any,
      paint: {
        "circle-color": [
          "match", agreeCat,
          "both", "rgb(150,25,40)",
          "ms_only", "rgb(40,110,205)",
          "cems_only", "rgb(235,125,20)",
          "rgb(165,170,178)", // agree_none
        ],
        "circle-opacity": ["case", ["==", agreeCat, "agree_none"], 0.43, 0.92],
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 1.6, 15, 6],
        "circle-stroke-width": 0,
      },
    } as any);
    map.on("mousemove", "bpm-agree-overlap", (e: any) => {
      const p = e.features?.[0]?.properties;
      if (!p) return hideTip();
      const cat =
        p.ms_dmg && p.cems_dmg ? "both" : p.ms_dmg ? "ms_only" : p.cems_dmg ? "cems_only" : "agree_none";
      showTip(e.point.x, e.point.y, AGREEMENT[cat]?.label ?? cat);
    });
    map.on("mouseleave", "bpm-agree-overlap", hideTip);
  }

  // Show the agreement layers only in the agreement view.
  function syncAgreement() {
    const on = state.view === "agreement" && state.show.buildings;
    for (const id of ["bpm-agree-context", "bpm-agree-overlap"])
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
  }

  // Coverage extents + CEMS not-analysed gaps as native MapLibre layers (GeoJSON from
  // platinum meta — replaces the deck.gl GeoJsonLayers). Outline-only extents on
  // purpose: a filled AOI would intercept hover from the admin units beneath it, so
  // the coverage tooltip only shows near the boundary (line hit = stroke only).
  function syncExtents() {
    for (const s of Object.keys(SOURCE_LABEL)) {
      const ext = extentCache.get(s);
      const srcId = `ext-src-${s}`;
      const lyrId = `ext-line-${s}`;
      if (ext && !map.getSource(srcId)) {
        const c = SOURCE_COLOR[s] ?? [80, 80, 80];
        map.addSource(srcId, { type: "geojson", data: ext });
        map.addLayer({
          id: lyrId,
          source: srcId,
          type: "line",
          layout: { visibility: "none" },
          paint: { "line-color": `rgba(${c[0]},${c[1]},${c[2]},0.92)`, "line-width": 2 },
        } as any);
        map.on("mousemove", lyrId, (e: any) => {
          const p = e.features?.[0]?.properties;
          if (p) showTip(e.point.x, e.point.y, extentTip(s, p));
          else hideTip();
        });
        map.on("mouseleave", lyrId, hideTip);
      }
      if (map.getLayer(lyrId))
        map.setLayoutProperty(
          lyrId, "visibility",
          state.show.extent && state.sources.has(s) ? "visible" : "none",
        );
    }
    // CEMS not-analysed (cloud / no imagery) gaps — filled, since they sit INSIDE the
    // CEMS AOIs and mark holes rather than boundaries.
    if (coverageDetailData && !map.getSource("cems-gaps-src")) {
      map.addSource("cems-gaps-src", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: coverageDetailData.features.filter((f: any) => f.properties.kind === "not_analysed"),
        } as any,
      });
      map.addLayer({
        id: "cems-gaps-fill",
        source: "cems-gaps-src",
        type: "fill",
        layout: { visibility: "none" },
        paint: { "fill-color": "rgba(95,100,110,0.43)", "fill-outline-color": "rgba(95,100,110,0.63)" },
      } as any);
      map.on("mousemove", "cems-gaps-fill", (e: any) => {
        const p = e.features?.[0]?.properties;
        if (p)
          showTip(e.point.x, e.point.y,
            `Not analysed — cloud / no imagery<br>${p.aoi_name ?? ""} · ${p.product ?? ""}`);
        else hideTip();
      });
      map.on("mouseleave", "cems-gaps-fill", hideTip);
    }
    if (map.getLayer("cems-gaps-fill"))
      map.setLayoutProperty(
        "cems-gaps-fill", "visibility",
        state.show.extent && state.sources.has("copernicus_ems") ? "visible" : "none",
      );
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
    syncAgreement();
  }

  // Admin choropleth (v2): boundaries from admin PMTiles, values from hyparquet,
  // each unit coloured via setFeatureState. Reuses adminCache/byUnit/metricColor/
  // adminTip — only the data source + render path change. Being a real MapLibre
  // layer, it sits IN the stack (fixes the deck.gl "always on top of tiles" issue).
  const ADMIN_SERVING: "pmtiles" | "deckgl" = "pmtiles";

  async function setupAdmin() {
    if (ADMIN_SERVING !== "pmtiles") return;
    const tok = await getToken();
    const dir = eventDir(tok, EVENT_ID!);
    // values: read the slim admin facts parquet, pivot into adminCache (properties
    // only — geometry comes from the tiles now) so the existing logic is reused.
    const rows = (await parquetReadObjects({
      file: await asyncBufferFromUrl({
        url: `${dir}/values/facts-admin.parquet?${tok.sas}`,
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
        url: `pmtiles://${dir}/admin-adm${lvl}/adm${lvl}.pmtiles?${tok.sas}`,
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

  // --- H3 (v2): hex-cell polygons pre-generated in the pipeline (ADR-0011) served as
  // PMTiles; per-source values via hyparquet; cells coloured via setFeatureState —
  // exactly the admin-choropleth pattern. Replaces deck.gl H3HexagonLayer.
  let h3ByCell: Map<string, any> = new Map(); // last applied state, for hover tips

  async function setupH3() {
    const tok = await getToken();
    const dir = eventDir(tok, EVENT_ID!);
    const labelId = map.getStyle().layers?.find((l: any) => l.type === "symbol")?.id;
    map.addSource("pmt-src-h3", {
      type: "vector",
      url: `pmtiles://${dir}/h3/h3_cells.pmtiles?${tok.sas}`,
      promoteId: "h3",
    });
    map.addLayer({
      id: "pmt-h3-fill",
      source: "pmt-src-h3",
      "source-layer": "h3_cells",
      type: "fill",
      layout: { visibility: "none" },
      paint: {
        "fill-color": ["coalesce", ["feature-state", "color"], "rgba(0,0,0,0)"],
        "fill-opacity": 0.6,
      },
    } as any, labelId);
    map.on("mousemove", "pmt-h3-fill", (e: any) => {
      const id = e.features?.[0]?.properties?.h3;
      const r = id && h3ByCell.get(id);
      if (r) showTip(e.point.x, e.point.y, tip(`${SOURCE_LABEL[r._src] ?? r._src} · highest here`, r));
      else hideTip();
    });
    map.on("mouseleave", "pmt-h3-fill", hideTip);
  }

  let _h3AppliedSig = "";
  function applyH3State(byCell: Map<string, any>, m: string, hMax: number) {
    h3ByCell = byCell;
    // ~115k setFeatureState calls is the expensive path in this app, and buildLayers
    // re-runs on every response during a refresh (incremental paint) — only re-apply
    // when the result would actually differ.
    const sig = `${m}|${hMax}|${byCell.size}|${[...state.sources].sort().join()}`;
    if (sig === _h3AppliedSig) return;
    _h3AppliedSig = sig;
    map.removeFeatureState({ source: "pmt-src-h3", sourceLayer: "h3_cells" });
    for (const [cell, r] of byCell) {
      const c = metricColor(m, r._v, hMax);
      map.setFeatureState(
        { source: "pmt-src-h3", sourceLayer: "h3_cells", id: cell },
        { color: `rgb(${c[0]},${c[1]},${c[2]})` },
      );
    }
  }

  function syncH3() {
    const vis = state.show.h3 && state.sources.size ? "visible" : "none";
    if (map.getLayer("pmt-h3-fill")) map.setLayoutProperty("pmt-h3-fill", "visibility", vis);
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

  // Excel export: built in the browser with exceljs from platinum artifacts (ADR-0011).
  // Classic (App Service) builds serve /api/export.xlsx from the same backend that serves
  // /api/token, so TOKEN_URL there stays the relative default — that backend is a real
  // fallback on export failure, but ONLY for Venezuela: /api/export.xlsx is hardcoded to
  // adm0="VE" (api/main.py) and was never made multi-event-aware. A client failure for any
  // OTHER event must not silently hand the user a Venezuela spreadsheet — it gets the same
  // loud failure the SWA build (no server fallback at all) shows.
  {
    const exp = document.getElementById("export") as HTMLAnchorElement | null;
    const hasServerFallback =
      TOKEN_URL === "/api/token" && ev.event_id === LEGACY_SERVER_EVENT; // classic build, AND this is the one event it can serve
    if (exp) {
      exp.addEventListener("click", async (e) => {
        e.preventDefault();
        const label = exp.textContent;
        exp.textContent = "⏳ Building spreadsheet…";
        try {
          const { downloadExport } = await import("./export");
          const tok = await getToken();
          await downloadExport(tok, eventDir(tok, EVENT_ID!), ev);
        } catch (err) {
          console.error("client export failed:", err);
          if (hasServerFallback) {
            window.location.href = exp.href; // classic build, Venezuela only: server fallback
          } else {
            exp.textContent = "⚠ Export failed — reload and retry";
            alert(`Spreadsheet export failed: ${err}. Reload the page and try again.`);
            return; // keep the error label
          }
        } finally {
          if (!exp.textContent?.startsWith("⚠")) exp.textContent = label;
        }
      });
    }
  }

  // Add each "pmtiles" source's MapLibre layers (hidden until shown by syncPmtiles)
  // and wire their hover. The read SAS + catalog base URL come from /api/token.
  async function setupPmtiles() {
    const converted = Object.entries(LAYER_SERVING).filter(([, v]) => v.mode === "pmtiles") as [
      string,
      Extract<Serving, { mode: "pmtiles" }>,
    ][];
    if (!converted.length) return;
    const tok = await getToken();
    const dir = eventDir(tok, EVENT_ID!);
    for (const [s, v] of converted) {
      const src = `pmt-src-${s}`;
      map.addSource(src, { type: "vector", url: `pmtiles://${dir}/${v.file}?${tok.sas}` });
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
    const tok = await getToken();
    const dir = eventDir(tok, EVENT_ID!);
    map.addSource("usgs", {
      type: "geojson",
      data: `${dir}/usgs/shakemap.geojson?${tok.sas}`,
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
  // Reduce, not Math.max(1, ...arr): spreading a large array (H3 can be >100k cells,
  // widest for broad-coverage sources like LIST) overflows the call-stack arg limit.
  const maxBy = (arr: any[], get: (x: any) => number) =>
    arr.reduce((m, x) => {
      const v = get(x);
      return !Number.isNaN(v) && v > m ? v : m;
    }, 1);
  const hasCov = (p: any) => (p?.coverage_fraction ?? 0) > 0;
  // Detected-only sources (no coverage) still contribute cells where damage was found;
  // include those so their damaged H3 cells render on the count metric.
  const hasData = (p: any) => hasCov(p) || (p?.damaged_detected ?? 0) > 0;

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

    const adminFeats = sources.flatMap((s) =>
      (adminCache.get(`${s}:${state.adminLevel}`)?.features ?? []).filter((f: any) => hasData(f.properties)),
    );
    const aMax = maxBy(adminFeats, (f) => metricValue(f.properties, m) ?? 0);
    const h3All = sources.flatMap((s) => (h3Cache.get(s) ?? []).filter(hasData));
    const hMax = maxBy(h3All, (r) => metricValue(r, m) ?? 0);

    // admin aggregation: ONE layer, each unit coloured by the MAX metric value across
    // the selected sources (recomputed as sources toggle). Hover shows the per-source
    // breakdown (adminTip), so you still see which source drove the max.
    if (state.show.admin && sources.length) {
      const byUnit = new Map<string, { f: any; v: number | null }>();
      for (const s of sources) {
        for (const f of adminCache.get(`${s}:${state.adminLevel}`)?.features ?? []) {
          if (!hasData(f.properties)) continue;
          const v = metricValue(f.properties, m);
          const cur = byUnit.get(f.properties.unit_id);
          if (!cur) byUnit.set(f.properties.unit_id, { f, v });
          else if (v != null && (cur.v == null || v > cur.v)) {
            cur.f = f;
            cur.v = v;
          }
        }
      }
      applyAdminState(byUnit, m, aMax); // colour the MapLibre admin layer in-place
    }

    // h3: ONE layer, each cell coloured by the MAX metric value across selected sources.
    if (state.show.h3 && sources.length) {
      const byCell = new Map<string, any>();
      for (const s of sources) {
        for (const r of h3Cache.get(s) ?? []) {
          if (!hasData(r)) continue;
          const v = metricValue(r, m);
          const cur = byCell.get(r.h3);
          if (!cur || (v != null && (cur._v == null || v > cur._v)))
            byCell.set(r.h3, { ...r, _v: v, _src: s });
        }
      }
      applyH3State(byCell, m, hMax); // hex tiles + feature-state (was deck.gl H3HexagonLayer)
    }

    // agreement view: served from the buildings PMTiles (see bpm-agree-* layers) —
    // the deck.gl ScatterplotLayer path was retired with /api/agreement.

    // coverage extents + CEMS gaps are native MapLibre layers now — see syncExtents().

    syncPmtiles();
    syncBuildings();
    syncAdmin();
    syncUsgs();
    syncExtents();
    syncH3();
  }

  // Sources with no native (own) geometry — raster products. In the native view they
  // have nothing per-building to draw, so we say so rather than show a blank map.
  // (Remove a source here once it gains a native layer — e.g. LIST when its raster
  // cells are polygonised into a native-list tile.)
  const NO_NATIVE_SOURCES = new Set(["list"]);
  function updateNativeNote() {
    const note = document.getElementById("native-note")!;
    const affected =
      state.view === "native" && state.show.buildings
        ? [...state.sources].filter((s) => NO_NATIVE_SOURCES.has(s))
        : [];
    if (affected.length) {
      const names = affected.map((s) => SOURCE_LABEL[s] ?? s).join(", ");
      note.textContent = `${names}: raster source — no per-building native geometry. Shown in the Overture base and admin / H3 views.`;
      note.hidden = false;
    } else {
      note.hidden = true;
    }
  }

  function renderLegend() {
    const lg = document.getElementById("legend")!;
    if (state.view === "agreement" && agreementCounts) {
      const c = agreementCounts;
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
    let props: any[] = [];
    for (const s of state.sources) {
      if (state.show.admin)
        props = props.concat(
          (adminCache.get(`${s}:${state.adminLevel}`)?.features ?? [])
            .map((f: any) => f.properties)
            .filter(hasData),
        );
      // concat, not push(...arr): spreading a large H3 array overflows the stack.
      if (state.show.h3) props = props.concat((h3Cache.get(s) ?? []).filter(hasData));
    }
    return maxBy(props, (p) => metricValue(p, metric) ?? 0);
  }

  // --- data --------------------------------------------------------------------
  async function ensureH3(source: string) {
    // Per-source values parquet from platinum — already WIDE ({h3, <metric>: value}),
    // the exact row shape the old API returned, so hMax/legend logic is reused as-is.
    if (h3Cache.has(source)) return;
    const tok = await getToken();
    const dir = eventDir(tok, EVENT_ID!);
    const rows = (await parquetReadObjects({
      file: await asyncBufferFromUrl({
        url: `${dir}/values/facts-h3-${source}.parquet?${tok.sas}`,
      }),
    })) as any[];
    h3Cache.set(source, rows);
  }
  async function ensureExtent(source: string) {
    if (!extentCache.has(source)) extentCache.set(source, (await getExtents())[source]);
  }
  async function ensureCoverageDetail() {
    if (!coverageDetailData) coverageDetailData = await fetchMeta("coverage_detail.json");
  }

  async function refresh() {
    const status = document.getElementById("status")!;
    try {
      const tasks: Promise<any>[] = [];
      for (const s of state.sources) {
        if (state.show.h3) tasks.push(ensureH3(s));
        if (state.show.extent) tasks.push(ensureExtent(s));
        if (state.show.extent && s === "copernicus_ems") tasks.push(ensureCoverageDetail());
      }
      if (state.show.buildings && state.view === "agreement") tasks.push(ensureAgreementCounts());

      const total = tasks.length;
      let done = 0;
      const tick = () => {
        const pct = total ? (done / total) * 100 : 100;
        status.innerHTML =
          `<div class="load-row"><span>Loading…</span><span>${done}/${total}</span></div>` +
          `<div class="pbar"><div class="pfill" style="width:${pct}%"></div></div>`;
      };
      if (total) tick();
      // Paint immediately with whatever is already cached, then repaint as each
      // response lands — the slowest overlay request (extents/coverage on a cold
      // server) no longer gates the whole map (ADR-0021 option 1). The choropleth
      // is independent of these tasks and unaffected either way.
      buildLayers();
      renderLegend();
      updateNativeNote();
      await Promise.all(
        tasks.map((t) =>
          t.then((r) => {
            done++;
            if (total) tick();
            buildLayers();
            renderLegend();
            return r;
          }),
        ),
      );
      buildLayers();
      renderLegend();
      updateNativeNote();
      status.textContent = ""; // clear the transient load line (the Current view caption was removed)
    } catch (e) {
      status.textContent = `Failed to load: ${e}`;
    }
  }

  // --- init + wiring -----------------------------------------------------------
  const el = (id: string) => document.getElementById(id)!;

  // Panel title from the event registry: name + CEMS activation id when present.
  function renderEventTitle(ev: EventInfo) {
    const cems = ev.external_ids?.cems_activation;
    el("event-title").textContent = cems ? `${ev.name} (${cems})` : ev.name;
  }

  // Event switcher: every registry event, current one selected. Picking another is
  // a full hash change + reload — no in-place teardown of this event's map sources
  // and layers (YAGNI). Setting location.hash alone is enough: the module-level
  // hashchange listener does the reload, so there's exactly one reload per switch,
  // not two. ⚠️4 any future in-page #anchor would full-reload; router-only hashes
  // for now.
  function renderEventSwitch(ev: EventInfo, events: EventInfo[]) {
    const sel = document.getElementById("eventSwitch") as HTMLSelectElement | null;
    if (!sel) return;
    sel.innerHTML = events
      .map(
        (e) =>
          `<option value="${esc(e.event_id)}"${e.event_id === ev.event_id ? " selected" : ""}>${esc(e.name)}</option>`,
      )
      .join("");
    sel.addEventListener("change", () => {
      location.hash = `#/e/${sel.value}`;
    });
  }

  // Populated immediately (not gated on map "load"): the dropdown and the
  // methodology note only need ev/events, not the map.
  renderEventSwitch(ev, events);
  const methodsEventNote = document.getElementById("methods-event-note");
  if (methodsEventNote)
    methodsEventNote.textContent = `Source notes reference the ${ev.name} response where event-specific.`;

  async function init() {
    // Registry lookup already happened in boot() — ev/events are initViewer's
    // closure parameters here, not re-fetched. events.json is the one platinum read
    // that stays at the tier root (not event-scoped) — every other read below goes
    // through eventDir(tok, EVENT_ID!) (tok is re-fetched from the module-level
    // memoized getToken() wherever it's needed).
    map.fitBounds([[ev.bbox[0], ev.bbox[1]], [ev.bbox[2], ev.bbox[3]]], { padding: 40, duration: 0 });
    renderEventTitle(ev);
    // PMTiles/hyparquet setup is additive — a failure must never blank the app.
    for (const [name, fn] of [
      ["pmtiles", setupPmtiles],
      ["buildings", setupBuildings],
      ["admin", setupAdmin],
      ["h3", setupH3],
      ["usgs", setupUsgs],
    ] as const) {
      try {
        await fn();
      } catch (e) {
        console.error(`v2 ${name} setup failed:`, e);
      }
    }
    const meta = await fetchMeta("sources.json");
    const sources: string[] = meta.sources;
    METRICS = [
      { key: "damage_rate_detected", label: "Damage fraction" },
      { key: "coverage_fraction", label: "Coverage" },
      { key: "damaged_detected", label: "Damaged buildings" },
    ];
    const ordered = [...sources].sort((a, b) => sourceRank(a) - sourceRank(b));
    state.sources = new Set(ordered);

    el("sources").innerHTML = ordered
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
          syncMetricLock();
          await refresh();
        }),
      );

    // Select-all / deselect-all: flip every source box, then one refresh.
    const setAllSources = async (on: boolean) => {
      el("sources")
        .querySelectorAll<HTMLInputElement>("input[data-source]")
        .forEach((box) => {
          box.checked = on;
          if (on) state.sources.add(box.dataset.source!);
          else state.sources.delete(box.dataset.source!);
        });
      syncMetricLock();
      await refresh();
    };
    el("src-all").addEventListener("click", () => setAllSources(true));
    el("src-none").addEventListener("click", () => setAllSources(false));

    syncMetricLock();
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

  // UNEP / HotOSM / DISHA carry no coverage or analysed rate, so damage-fraction and
  // coverage are meaningless for them. When the selection is ONLY those (any combo,
  // nothing else), lock "colour aggregation by" to the damaged count and grey it out.
  const COUNT_ONLY_SOURCES = new Set(["unep_debris", "hot_osm", "disha"]);
  function syncMetricLock() {
    const sel = el("metric") as HTMLSelectElement;
    const countOnly =
      state.sources.size > 0 && [...state.sources].every((s) => COUNT_ONLY_SOURCES.has(s));
    if (countOnly && state.metric !== "damaged_detected") {
      state.metric = "damaged_detected";
      sel.value = "damaged_detected";
    }
    sel.disabled = countOnly;
  }

  document.querySelectorAll<HTMLInputElement>("input[data-layer]").forEach((box) =>
    box.addEventListener("change", async () => {
      state.show[box.dataset.layer!] = box.checked;
      syncSubControls();
      await refresh();
    }),
  );

  map.on("load", init);
}

// Programmatic hash edits use location.hash = ... (pushes a new history entry,
// preserving Back); this listener is what makes URL edits, Back, and Forward
// correct without a client-side router — each hash change just reloads fresh.
window.addEventListener("hashchange", () => location.reload());

function hideViewer() {
  (document.getElementById("map") as HTMLElement).hidden = true;
  (document.getElementById("panel") as HTMLElement).hidden = true;
  (document.getElementById("methods-open") as HTMLElement).hidden = true;
}

// The hash is known synchronously, before any async token/registry fetch — hide
// the viewer chrome immediately for the empty-hash (landing) case so there's no
// flash of the map/panel shell while boot() is still in flight. (An unknown-but-
// non-empty id, e.g. #/e/garbage, can't be resolved this early — the registry is
// the only authority on that, so that one flash is unavoidable without it.)
if (!currentEventId()) hideViewer();

async function boot() {
  const tok = await getToken();
  const events = await fetchEvents(tok);
  const landing = document.getElementById("landing")!;
  // Zero events is a real, valid state of the registry — not a failure — and
  // must read as information, not an error (never render identically to the
  // registry-unreachable/malformed case caught below).
  if (events.length === 0) {
    hideViewer();
    renderEmptyRegistry(landing);
    return;
  }
  if (EVENT_ID === null) {
    hideViewer();
    renderLanding(events, landing);
    return;
  }
  const ev = events.find((e) => e.event_id === EVENT_ID);
  if (!ev) {
    hideViewer();
    renderEventError(EVENT_ID, events, landing);
    return;
  }
  initViewer(ev, events);
}
boot().catch((err) => {
  // Token fetch failed, events.json is unreachable, or it didn't validate
  // (fetchEvents's own "malformed registry" Error) — a real failure, distinct
  // from the empty-registry case above. Never leave a silent blank/white shell.
  console.error("boot failed:", err);
  hideViewer();
  renderBootError(err instanceof Error ? err.message : String(err), document.getElementById("landing")!);
});

// --- methodology slide-over: glass panel of how the map is built + per-source cards ---
// TODO(product-history): surface each source's product version + availability dates
// (e.g. OSU v0 25 Jun -> v1 1 Jul) as a small per-source timeline, not just the latest.
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
    tag: "SAR-based (radar)",
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
    tag: "SAR-based (radar)",
    blurb:
      "Oregon State University Sentinel-1 coherence analysis (v1 product, published 11 Jul 2026). Loss of radar coherence indicates damage; the v1 update expanded coverage of the strong-shaking zone.",
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
    tag: "AI · per-building",
    blurb:
      "DISHA (Data Insights for Social & Humanitarian Action) detects damaged buildings from pre/post satellite imagery over NW Caracas, on Google Open Buildings footprints.",
    note: "Preview over a small AOI; provider validation pending.",
  },
  {
    key: "unep_debris",
    tag: "SAR-based (radar)",
    blurb:
      "UNEP/OCHA Joint Environment Unit building-debris assessment. Sentinel-1 radar change detection estimates the debris mass — in tonnes — generated by each damaged building.",
    note: "The only source carrying debris mass: roughly 17 million tonnes across ~96,000 damaged buildings.",
  },
  {
    key: "uh",
    tag: "AI · per-building",
    blurb:
      "Deep learning model by Singh and Hoskere classifying Overture building footprints using pre- and post-event imagery (covers 478K individual buildings) — across eight coastal AOIs, including Aragua/Carabobo towns no other per-building source covers.",
    note: "Coverage and damage fraction come from its own per-building classifications (no AOI polygon). More at <a href='https://quakedamage.github.io' target='_blank' rel='noopener'>quakedamage.github.io</a>.",
  },
  {
    key: "list",
    tag: "AI · per-building",
    blurb:
      "A WFP collaboration with LIST and CERN: a deep-learning (ResNet) model predicting per-building damage from pre/post SAR imagery, sampled onto Overture footprints. Only the model's strongest damage class is shown.",
    note: "The methodology is still under refinement, and the results may be subject to further improvements. A preliminary screen to triangulate, not a confirmed count.",
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
