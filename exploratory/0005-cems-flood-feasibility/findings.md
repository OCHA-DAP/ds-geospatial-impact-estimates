# 0005 — Feasibility: scraping all historical CEMS flood activations

**Question.** Can we comprehensively scrape Copernicus EMS Rapid Mapping data for
*all* flood activations (not just single events like EMSR884/EMSR916), and what
would that involve?

**Answer: yes.** Full history 2012→present is reachable through two public
endpoints, the flood-extent layer is locatable across every naming era with a
4-pattern matcher (35/36 stratified sample; the one miss is a genuine
"flood receded / void imagery" product, not a scrape failure), and the total
volume is modest (~3,300 zips ≈ 30 GB).

## Method

`analysis.py` (staged, cached to `/tmp/gie_cems_flood_poc`):

1. **inventory** — activation lists from both portals, cross-validated.
2. **legacy-manifest** — crawl every legacy flood activation page on the
   archive portal; parse product cards → vector-zip links.
3. **new-manifest** — `ocha_lens.cems.get_products()` for every new-portal flood.
4. **poc** — stratified sample (~3 activations/year, 2012–2023), download one
   delineation zip each, locate + read the flood-extent layer, compute
   feature count and dissolved area.

## Finding 1 — one portal is not enough; two are

| Source | Coverage | Interface |
|---|---|---|
| New portal `rapidmapping.emergency.copernicus.eu/backend/dashboard-api/` (what `ocha-lens` wraps) | **EMSR656+ only** (Mar 2023→) | JSON; product zips from same backend |
| Archive portal `mapping.emergency.copernicus.eu/activations/api/activations/` | **EMSR001→current** (2012→) | DRF JSON (limit/offset) for the *list*; per-activation **HTML page** for product links; zips on S3 (`cems-mapping-website` bucket) |

- Archive list: **1,060 activations total; 302 EMSR floods (2012–2026)** —
  214 legacy + 88 new-portal era;
  ~20–40 floods/yr. 88 of those are new-portal era — the two portals **agree
  exactly** on that overlap (asserted in stage 1).
- Requests need a browser-ish `User-Agent` (default python UA → 403 on the new
  backend).
- `EMSN*` codes in the archive are the Risk & Recovery service (different
  product line; 3 flood-category entries) — excluded.
- 62 EMSR numbers appear in no portal (never-published activations) — not a gap
  we can or need to fill.

## Finding 2 — what a flood activation delivers

New-portal era (88 floods, 1,193 product rows): **DEL(ineation) is the flood
workhorse** — 72/88 activations have ≥1 delivered DEL; GRA 38/88 (adds
`builtUpP` damage points like the earthquake chain uses); FEP 12; REF 1.
~25% of product rows are status `N` (closed, nothing delivered) — 6 activations
delivered nothing at all. Legacy era: 2,410 vector zips across 206 activations;
titles map cleanly to {Delineation, Grading, Reference, First Estimate}.

Product zips contain per-layer shapefiles (+ since ~2020 GeoJSON copies of
each). The **flood extent** lives in one layer per era:

| Era | Extent layer name | Attrs | CRS |
|---|---|---|---|
| 2012–13 | `*_Crisis_event_A.shp`, `*_Event_A_M.shp` (heterogeneous; `_event_a` substring catches them) | UPPERCASE ESRI (`EVNT_TYPE`…) | UTM zone |
| ~2014–16 | `*_crisis_information_poly.shp` | `subtype`, `grading`, `interpret` | UTM zone |
| ~2017–18 | `*_observed_event_a.shp` | `event_type, obj_desc, det_method, notation, dmg_src_id` | 4326 |
| ~2019–23 | `*_observedEventA_r1_v*.shp` | same + `area` | 4326 |
| 2023+ (new portal) | `*_observedEventA_v*.shp` | same | 4326 |

Supplementary layers in some 2025+ DELs: `floodDepthA`, `maximumFloodExtentA`,
`modelledEventA`. Coverage layers (`areaOfInterestA`/`imageFootprintA`/
`notAnalysedA` and era equivalents) exist throughout — needed to distinguish
"not flooded" from "not analysed", same trick as `cems_coverage.py`.

## Finding 3 — PoC hit rate and the absence case

Stratified sample, one delineation zip per activation, ~3 activations per year
2012–2023: **35/36 zips → extent layer found, read, reprojected, area computed**
(plus 7/7 new-portal-era zips in initial probing). The single miss
(EMSR231 MONIT03, Ireland 2017) contains only a satellite footprint and a
"ZD020 Void Collection Area / Missing data" polygon — the flood had
receded/imagery was void. That is a *real state* monitoring products can be in:
the harvester must record "no event layer in this product" as information, not
error, and rely on the coverage layers to say what was actually observed.

## Finding 4 — known gaps (small, enumerable)

- **7 legacy flood activations** (EMSR129, 321, 384, 451, 473, 474, 519) have
  products per the API metadata but an **empty archive page** — never migrated.
  S3 direct-key guessing and the new backend both fail. Only recovery path
  found: Wayback Machine captures of the old `emergency.copernicus.eu/mapping`
  site. 7/214 ≈ 3% of legacy activations; decide later if worth chasing.
- EMSR364 has genuinely 0 products (nothing delivered).

## Finding 6 — imagery acquisition date/time (the ML-label requirement)

For flood labels we need per-polygon acquisition datetimes (multiple images and
digitizations per activation, per product, even per polygon via `dmg_src_id`).
Audited era by era against real packages:

| Era | Where the acquisition datetime lives | Precision |
|---|---|---|
| A 2012–13 | **on every polygon**: `SRC_DATE` (+ `EXT_DATE`) | date |
| B 2014–16 | **on every polygon**: `src_date`; time often in `src_info` ("COSMO-SkyMed 01/06/2016 17:50") | date, often minute |
| C 2017–18 | **in-package `source` DBF** (see correction below) | minute |
| D 2019–23 | **in-package `source` DBF** (see correction below) | minute |
| E 2023+ | **new-portal API**: each product's `images[]` carries `sensorName` + `acquisitionTime` to the minute (also encoded in image `fileName`) | minute |

**CORRECTION (2026-09-01).** The initial audit missed a geometry-less
**`source` DBF** shipped in every 2017+ package (`*_source*_v*.dbf`) — the
layer scan only globbed `.shp` members. It carries, per source image:
`src_id` (joining polygons' `dmg_src_id`), `source_nam`, `src_date`,
`source_tm` (minute), `sensor_gsd`, `eventphase` — matching the official
Crisis Information Package data model
(mapping.emergency.copernicus.eu/…/vector-package/, JRC121741). The
in-package join gives era C/D **minute precision** (validated: EMSR293,
EMSR459, EMSR574 → 100% minute) and disambiguates multi-image 2023+ products.

The earlier catalog-match idea is retracted as the primary mechanism: on
EMSR574 the STAC search proposed a Sentinel-1 pass, but the source table
shows the actual image was **RADARSAT-2** (2022-05-15 08:44 UTC), which no
public catalog serves — catalog matching would have silently mislabeled it.
It remains a validation cross-check only. Wayback product pages carry only
publish times; the map PDF title block is rasterized (OCR-only).

Implication for silver: the canonical extent schema needs
`acq_datetime` + `acq_precision` (exact / date / window) + `acq_method`
(attribute / api / catalog-match / unknown) so label consumers can filter by
the precision they can tolerate — a window-only date is information, not an
error, but it must be distinguishable.

## Scale

~2,410 legacy vector zips + ~892 new-portal delivered zips ≈ **3,300 zips,
~30 GB** (mean 9.2 MB over 50 sampled). A polite serial crawl is hours, not days.

## Finding 5 — selective download works (HTTP range into the zips)

Full zips are mostly reference layers, KMZ/SLD/PDF baggage, and (new era)
GeoJSON duplicates; the flood-extent layer is a small fraction. Both zip hosts
sit on S3 and honor `Range` (`cems-mapping-website` directly; the new backend
302s to a presigned `rapidmapping.s3.amazonaws.com` URL — resolve the redirect,
then range against S3). So a remote-zip reader (`remotezip`) can fetch the
central directory + only the extent/coverage members (`--stage selective`):

| Product | Full zip | Selective | Extent feats |
|---|---|---|---|
| EMSR009 2012 (era A) | 3.2 MB | 1.40 MB | 3,630 |
| EMSR149 2016 (era B) | 20.1 MB | 8.67 MB | 202 |
| EMSR258 2018 (era C) | 4.1 MB | 0.63 MB | 225 |
| EMSR557 2022 (era D) | 1.5 MB | 0.01 MB | 27 |
| EMSR657 2023 (new) | 5.5 MB | 0.06 MB | 75 |
| EMSR871 2026 (new) | 6.4 MB | 0.06 MB | 49 |

Modern products (2019+) shrink ~99%; the 2014–16 era only ~50–70% because its
`crisis_information_poly` is an everything-layer. Expected corpus transfer:
**roughly 3–7 GB instead of ~30 GB**, at the cost of ~5–15 HTTP range requests
per zip instead of 1 (still trivial vs 3,300 full downloads). Every selectively
fetched layer was re-read with geopandas to confirm integrity.

Trade-off to note: selective download means we do NOT hold the full raw zip,
which weakens the archive-as-insurance argument (the 7 lost legacy activations
show CEMS history does disappear). Options: selective-only, full-zip archive,
or hybrid (full zips for the products we harmonize, selective for the rest).
The new-portal per-layer API is no alternative — it serves vector tiles/COGs
for map display, not bulk vectors.

## What this feeds (architecture discussion, deliberately not decided here)

- Reuse per-event bronze layout (`bronze/event=…/source=copernicus_ems/…`) vs. a
  new activation-keyed corpus layout (`source=copernicus_ems/code=EMSRnnn/…`) —
  302 floods won't map 1:1 onto `events.yaml`.
- Legacy-vs-new split: extend `ocha-lens` with an archive-portal module
  (team-standard home) vs. keep the archive scraper repo-local.
- Which zips to pull: extent needs DEL only (+GRA where DEL absent); GRA also
  carries `builtUpP` damage grading compatible with the earthquake chain.
- Harmonization: 5 schema eras → one canonical extent schema; keep
  per-monitoring time series (flood evolution) vs. latest-only; era A/B
  attribute mapping needs a closer look before trusting `event_type` semantics.
- The `--stage poc` sample covers ~36 of 3,300 zips; a full-corpus dry run
  (download-and-match only, no harmonization) is the obvious next validation.

## Repro

```sh
uv run --group etl python exploratory/0005-cems-flood-feasibility/analysis.py            # all stages
uv run --group etl python exploratory/0005-cems-flood-feasibility/analysis.py --stage poc
```

Needs network only (public endpoints, no credentials). `beautifulsoup4` is in
the lockfile (transitive); if it ever drops out, add `--with beautifulsoup4`.
