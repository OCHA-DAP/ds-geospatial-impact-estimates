# Multi-event foundation: event registry, partitioning, and viewer

**Date:** 2026-08-14
**Status:** approved (design discussion 2026-08-12 → 2026-08-14)
**Driver:** a new earthquake in Colombia requires the viewer and data lake —
built for a single event (Venezuela, `adm0=VE`) — to support multiple events
in multiple countries, without breaking anything currently live.

## Decisions taken during design

- **Foundation first**: build the multi-event architecture properly and ingest
  Colombia into the new layout from day one, rather than bolting Colombia on
  and migrating later.
- **Contributor upload portal is deferred** to its own spec. Decision recorded
  for that future work: uploads will be invite-gated for known partners (not
  open, not full account auth).
- **App Service dependency**: verified (source + deploy workflow + live prod
  bundle) that the SWA's only remaining App Service dependency is the XLSX
  export *fallback* URL. Severing it is step 1.

## Out of scope

- Contributor upload portal (own spec later; invite-gated).
- App Service retirement (separate decision; this work must not depend on it).
- Path-based routing and the custom domain *implementation* (the domain is a
  DNS/IT request fired in parallel; hash routes convert to path routes
  mechanically when the App Service is retired).
- Raw-data download surface for external users.

## 1. Sever the App Service fallback (first, standalone PR)

The SWA build stops setting `VITE_API_BASE` in `swa-deploy.yml`. In
`web/src/main.ts`, the export catch-block currently redirects to
`${API_BASE}/api/export.xlsx` on client-export failure; with no `API_BASE`
configured it must **surface an explicit error to the user** (fail loudly),
never navigate to an empty href. The classic App Service build sets no
`VITE_API_BASE` and falls back to same-origin — its behavior is unchanged.

After this PR the SWA's only external dependencies are the token issuer and
blob storage. All multi-event work then proceeds with zero App Service
coupling.

## 2. Event identity & registry

- **Event ID**: `<yyyymmdd>-<countries>-<hazard>` from event onset (UTC),
  e.g. `20260624-ve-earthquake`. Date-first keeps blob listings
  chronological; full date makes real collisions practically impossible (a
  same-day second quake in one country is operationally one response;
  aftershock products fold into the main event). The registry enforces
  uniqueness; a true collision gets a `-b` suffix.
- **The country and hazard segments are mnemonics, never parsed.** No code
  derives anything from the slug; the registry is the sole authority
  (`countries` list, `hazard` field). A multi-country event may combine
  codes (`20260812-co-ve-earthquake`) or use the primary country alone —
  editor's choice at registration. Any hazard slug works
  (earthquake/flood/cyclone/…).
- **External IDs are metadata, not identity**: GLIDE number (may lag onset by
  hours–days, hence not usable as our ID), GDACS ID, USGS ID, CEMS activation
  code(s) — all recorded per event for cross-linking.
- **Registry**: `events.yaml` checked into the repo (adding an event is a
  code-adjacent act — pipelines must run for it anyway; no database,
  consistent with ADR-0002). Fields per event: `event_id`, `name`, `hazard`,
  `onset` (ISO date), `countries` (list of adm0 codes), `bbox` (viewer
  fly-to), `status` (`active`/`closed`), external-ID fields above.
- `stage_serving.py` publishes the registry as `events.json` into platinum;
  the SPA reads it from there (same token-issuer read path as everything
  else — no issuer change needed, its SAS is directory-scoped at
  `.../platinum` and covers subdirectories).

## 3. Partitioning

`event=` becomes the first partition under each tier; `source=` and below are
unchanged beneath it:

```
bronze/event=20260810-co-earthquake/source=copernicus_ems/code=EMSR9xx/...
gold/event=20260810-co-earthquake/model=common/...
platinum/event=20260810-co-earthquake/...
```

(Colombia slug illustrative — fixed from the USGS onset date at registration.)

- **`adm0=` is dropped as a path segment for new events; country becomes a
  column.** Rationale: (a) cross-border deliveries arrive as one file —
  splitting them across country partitions at ingest would violate ADR-0005's
  as-received bronze; (b) no reader prunes by country — the viewer reads
  per-event, and column filters are free in DuckDB/hyparquet; (c) the
  registry's `countries` list carries the event↔country mapping.
- **CODAB boundaries stay outside the event tree** as shared, country-keyed
  reference data (`bronze/source=codab/adm0=XX/`), reusable across events. A
  second event in a covered country re-ingests nothing.
- **Code choke point**: `gie.config.blob_path()` / `az_path()` gain a
  required event argument; every pipeline gets a required `--event` flag with
  **no default** — a run that doesn't name its event fails loudly instead of
  silently writing the legacy layout. (Reference-data pipelines like
  `ingest_codab` are the exception: they write the shared tree and take no
  event.)
- The `platinum` vs `platinum-prod` tier split (ADR-0014) is orthogonal and
  unchanged: `platinum-prod/event=<id>/...`.
- ADR-0005's idempotent immutable-path ingestion carries over as-is; the
  event key is just part of the path.

An **ADR** is drafted alongside implementation (amends ADR-0005's path
scheme; records the adm0-as-column and registry decisions and rejected
alternatives).

## 4. Migration of the existing VE data — copy, never move

1. Server-side blob copy of the existing VE tree (bronze/silver/gold/
   platinum) into `event=20260624-ve-earthquake/` paths. Copied paths keep
   their existing `adm0=VE` segments — rewriting copied history buys nothing.
   The legacy un-evented tree is left untouched; everything live keeps
   reading it.
2. **Verification before any cutover**: blob count + total-size comparison
   between the legacy tree and the event-keyed copy, per tier.
3. The multi-event SPA ships through the existing rails: PRs touching `web/`
   already get SWA preview environments on the staging data tier — verify
   event-keyed reads there, then merge to prod.
4. Prod data cutover remains what it already is: `promote.py` copies to
   `platinum-prod`.

At no point does a live reader's data disappear from under it. The classic
App Service build stays pinned to the legacy layout until its own retirement
decision; it receives no multi-event changes.

## 5. Legacy-tree deprecation (after cutover verified in prod)

**Gate: the legacy tree cannot be deleted while the App Service is live** —
its server-side DuckDB reads legacy gold/silver paths (§4 pins it there). The
freeze clock therefore starts at the App Service retirement decision, not at
SWA cutover. Severing the SWA's last App Service dependency (§1) is what
makes that retirement decidable.

Entry in `data_ledger.md`: legacy un-evented tree *frozen* on date X, *delete
after* X + 4 weeks — then actually delete it on that date. Bronze under the
old paths is the only copy of some as-received products, so step 4.2's
verification gates the freeze. A lingering "just in case" copy is a latent
wrong-read a year later; deletion is the point.

## 6. Viewer: landing page + per-event hash routes

- `/` becomes a **landing page**: one card per event from `events.json`
  (name, onset, countries, status). Also the future home of the contributor
  entry point.
- The current viewer becomes the event view at **`#/e/<event_id>`** (hash
  routing — zero server/SWA-config changes, works identically on both hosts
  while the App Service exists). Deep-linkable per-event URLs are the point:
  responders share "the Colombia dashboard", not app-configuration steps.
- In-viewer event dropdown for switching; initial map view flies to the
  registry bbox.
- **Unknown event ID renders an explicit error card** — never a blank map,
  never a silent fallback to another event.
- Custom domain: SWA Free tier supports two custom domains with managed TLS;
  a CNAME from a CHD/OCHA-controlled domain is an IT request, queued in
  parallel, orthogonal to this work.

## 7. Colombia ingestion

Register the event in `events.yaml` (slug from USGS onset date), ingest CODAB
`adm0=CO` into the shared reference tree, then per-source ingest/harmonize
with `--event` as products arrive (new CEMS activation code, partner
deliveries). Cross-border products land whole under the event, countries as
columns.

## Error handling & testing

- Pipelines: required `--event` (no default); unknown event ID (not in
  `events.yaml`) is an immediate error naming the registry file.
- Registry: schema-validated on load (required fields, unique IDs, valid adm0
  codes); `stage_serving` refuses to publish an invalid registry.
- Unit tests: `blob_path()` event-aware path construction (all four tiers ×
  dev/prod tier suffix); registry validation (duplicate ID, missing field).
- Smoke: after VE copy, the count/size verification script's output is the
  recorded evidence for the freeze decision.
- Viewer: unknown-event error card; landing page renders from a fixture
  `events.json`.

## Sequencing

1. Sever-the-fallback PR (§1).
2. Registry + partitioning + `--event` pipelines (§2–3); VE tree copy +
   verification (§4).
3. Colombia ingestion (§7); landing page + hash routes (§6), verified on SWA
   preview → prod.
4. Legacy freeze-and-delete (§5). Custom-domain IT request in parallel.
   Upload portal: separate spec.
