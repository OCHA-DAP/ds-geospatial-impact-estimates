// Deploy-target config, resolved at BUILD time from Vite env vars.
//
// UNSET (every existing build, including the App Service pipeline): both fall back to
// same-origin relative paths, so the compiled fetch URLs are identical to the
// pre-config-switch code — the classic deployment's behavior is unchanged.
//
// The SWA build (ADR-0022 / ADR-0011 Phase 3) sets:
//   VITE_TOKEN_URL  full token-issuer endpoint incl. app/tier, e.g.
//                   https://chd-ds-token-issuer.azurewebsites.net/api/token?app=satellite-viewer&tier=prod
//   VITE_API_BASE   origin of the legacy App Service, for the /api routes that are not
//                   yet client-side (h3, agreement, coverage_detail, extent, sources,
//                   export, deck.gl-served layers), e.g.
//                   https://chd-ds-geospatial-impact-viewer.azurewebsites.net

export const TOKEN_URL: string = import.meta.env.VITE_TOKEN_URL || "/api/token";
export const API_BASE: string = import.meta.env.VITE_API_BASE || "";

// The legacy App Service's /api/export.xlsx is a pre-multi-event route hardcoded
// to Venezuela (api/main.py export_xlsx(adm0="VE")) — it cannot serve any other
// event. The classic-build export fallback may only fire for THIS event; every
// other event must see the same loud client-export failure the SWA build shows.
export const LEGACY_SERVER_EVENT = "20260624-ve-earthquake"; // the one event the legacy App Service /api/export.xlsx can serve — delete with the App Service
