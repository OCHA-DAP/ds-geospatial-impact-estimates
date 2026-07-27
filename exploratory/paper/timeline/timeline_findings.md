# Release / availability timeline — VEN earthquake damage products

*Draft output for paper §4.1 (latency reconstruction) and §6.1–6.2 (availability & latency
results). Reproduce with `build_timeline.py`; data table in `timeline_events.csv`.*

## Question
When did each satellite-derived damage product become **available**, measured from the earthquake?
And how confidently can we reconstruct that from what we hold locally, before asking providers?

## Clock zero
**USGS mainshock `us6000t7zp` (M7.5, 28 km SE of Yumare): 2026-06-24 22:05:11 UTC**
(18:05 local, VET = UTC−4). A M7.2 foreshock (`us6000t7zc`) struck **38 seconds earlier** — for
latency purposes the event is a single instant on 2026-06-24 evening. Source: USGS ComCat API
(authoritative).

## Method & evidence (what each anchor is worth)
Three date types, three confidence levels:

| Anchor | What it is | Confidence |
|---|---|---|
| **Mainshock origin** | USGS ComCat origin time | **HIGH** — authoritative |
| **Our-ingest** | git author-date of the first commit that ingested/integrated the product | **HIGH but it's an *upper bound*** — it marks *integration*, so the file reached us at-or-before this; and provider release is at-or-before that again |
| **Internal date** | product metadata (S1 acquisition, product datestamp) | **HIGH** for what it is (when the input was sensed, not when the product shipped) |
| **Provider release** | when the provider actually published | **NOT yet captured → confirm with providers / HDX** |

So the reconstructed latencies below are **conservative (upper-bound) operational-availability**
numbers: "how long until *we* could act on it." True provider-release latency is ≤ these and is
the open item. Cross-check: the git anchors agree with the day-level `data_ledger.md` `updated`
column on every row.

**Caveats.** (1) Commit timestamps carry mixed UTC offsets (−0600 for most; −0400 for the OSU PR
from another contributor) — all converted to UTC via each commit's own offset. (2) An "integration"
commit can lag actual receipt by hours-to-a-day (we ingest, then commit), so treat sub-day
precision loosely. (3) Products delivered incrementally (CEMS, Microsoft) have *several* dates, not
one — captured as separate milestone rows.

## The reconstructed timeline (upper-bound operational availability)

| Days | Our-ingest (UTC) | Product / milestone | Channel |
|---:|---|---|---|
| 1.82 | 2026-06-26 17:51 | **Microsoft** — Catia La Mar (first AOI) | HDX |
| 1.92 | 2026-06-26 20:10 | **CEMS EMSR884** — first delivered products *(reference std)* | CEMS portal |
| 2.70 | 2026-06-27 14:51 | Microsoft — +La Guaira +Caraballeda | HDX |
| 3.88 | 2026-06-28 19:17 | Microsoft — +2 more AOIs (5 total) | HDX |
| 3.94 | 2026-06-28 20:38 | **IMPACT v1** — S1 SAR damage-proxy *raster* | email |
| 4.81 | 2026-06-29 17:38 | **OSU/NASA** — S1 coherence damage | provider |
| 4.82 | 2026-06-29 17:41 | Microsoft — merged/deduplicated (all 5 AOIs) | HDX |
| 4.87 | 2026-06-29 19:01 | **HOT fAIr** — AI+crowd damage points | HDX |
| 6.95 | 2026-07-01 20:58 | **UNEP/OCHA JEU** — building-debris mass | HDX |
| 6.96 | 2026-07-01 21:08 | *USGS ShakeMap — MMI contours (context, not a damage product)* | USGS API |
| 7.96 | 2026-07-02 21:04 | **IMPACT v2** — S1 *vector* damage (supersedes v1) | email |
| 7.96 | 2026-07-02 21:04 | **DISHA (UNOPS)** — ML inference *(licence-restricted)* | provider |

*(Overture is a pre-event exposure base, release 2026-06-17.0 — excluded from latency ranking.)*

## Findings

1. **The whole response fits in one week.** Event to last major product = ~8 days; the field went
   from nothing to a dozen independent products in that window.

2. **First damage signal ≈ day 2 — and it was optical, not the reference.** Microsoft (day 1.8) and
   the first CEMS delivery (day 1.9) arrived nearly together. The reference standard was *not* the
   slowest thing — its *first* products were among the fastest.

3. **"CEMS is slow" is too crude — CEMS is a *stream*, not a release.** Its first map came at
   ~2 days, but grading was incremental (10 delivered / 9 pending as of 06-28) and only consolidated
   ~07-02 (~8 days). The honest framing for the paper: **fast first look (~2 d), complete grading
   (~8 d).** Whether a competing product beats CEMS depends heavily on *which CEMS snapshot* you
   compare against (ties to outline §4.3 decision).

4. **SAR arrived in two waves — the v1/v2 story is real and quantified.** IMPACT's S1 was *acquired*
   ~12–24 h post-event (06-25 10:15Z / 22:42Z) but the usable **raster proxy** reached us at day 3.9;
   the corrected **vector** product at day 8.0. So responders had a rough SAR hotspot screen ~4 days
   before the refined footprint-level product. That ~4-day accuracy-vs-latency gap within a single
   provider is one of the paper's cleanest illustrations.

5. **Sensing latency ≪ delivery latency.** S1 was overhead within a day; the product took 3–8 days.
   The bottleneck is processing/delivery, not revisit — an actionable point for the discussion.

6. **Channel splits the field.** Most products came via **HDX** (open, timestamped — good for
   confirming release dates); IMPACT via **email**; DISHA via a **restricted provider channel**.
   HDX rows are the easiest to upgrade from upper-bound to true-release.

7. **Availability ≠ usability (DISHA).** DISHA landed at day 8 *and* is licence-restricted (no public
   redistribution without UNOPS authorization) — a product can be "available" yet operationally
   constrained. This is an availability finding, not a footnote.

## What this feeds
- Paper §6.1 (availability) & §6.2 (latency): the timeline figure = event → each product's first
  availability → updates, with the v1→v2 and CEMS first-vs-consolidated arcs drawn explicitly.
- The **latency axis of the §6.5 latency–accuracy frontier** (x-values come from here).
- Outline §4.3 decision: pins *which* CEMS snapshot is the frozen reference (first vs consolidated
  changes every relative-latency claim).

## Open items — confirm with providers (to convert upper-bound → true release)
- [ ] **CEMS**: EMSR884 activation timestamp + per-product delivery dates (Copernicus portal is
      JS-rendered; pull via API/ocha-lens or ask CEMS). Anchors the whole reference timeline.
- [ ] **Microsoft**: HDX dataset first-published + per-AOI update timestamps.
- [ ] **IMPACT**: email delivery dates for v1 raster and v2 vector (we have S1 acquisition, not release).
- [ ] **OSU/NASA**: product release/delivery date.
- [ ] **HOT fAIr** & **UNEP/OCHA JEU**: HDX publish timestamps.
- [ ] **DISHA/UNOPS**: delivery date + exact licence terms bearing on what we may publish.
