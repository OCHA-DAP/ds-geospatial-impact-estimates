---
status: "accepted"
date: 2026-06-29
deciders: zackarno
---

# Switch the Microsoft source from per-AOI tiles to the merged deduplicated dataset

## Context and Problem Statement

We had been ingesting Microsoft AI for Good's building-damage predictions as
**five separate per-AOI tiles** (caraballeda_east, catia_la_mar, catia_la_mar_east,
la_guaira_and_surrounding, la_guaira_east), which overlap — so the same building
appears in multiple tiles, and we approximated the overlap by hand (a gold-level
`la_guaira_east → surrounding` supersession). Microsoft then published a single
**merged, deduplicated** dataset spanning all five AOIs (plus a unioned valid-area
mask) that does the dedup and reconciles multi-observation damage properly. Do we
adopt it, and does it supersede the per-AOI data?

## Decision Drivers

* More correct counts — no double-counted overlap, multi-observation damage reconciled.
* Simpler pipeline — drop the manual per-AOI supersession.
* Preserve provenance and keep a path open for future data of unknown shape.

## Decision Outcome

1. **Bronze:** land the merged files **raw, as received** (`.gpkg` / `.geojson`)
   under `bronze/source=microsoft/adm0=VE/merged/`. Keep the per-AOI bronze as
   historical raw. (`ingest_microsoft_merged.py`.)
2. **Silver:** re-derive the Microsoft silver from the merged set (reproject
   `32619 → 4326`), **replacing** the per-AOI `footprints.parquet` +
   `analysed_extent.parquet` with a drop-in schema, and **retire the manual
   supersession** — the merge already handles overlaps. (`harmonize_microsoft.py`.)
3. **One-off / uncertain cadence.** We do not yet know whether Microsoft will keep
   refreshing this merged dataset or also send individual AOI tiles not in it. So
   the per-AOI ingestion path stays available, and this is a **manual,
   re-runnable** step, not an automated feed.

### Consequences

* Good: simpler and more accurate; one deduplicated source instead of five
  overlapping ones; `catia_la_mar_east` matched the per-AOI count exactly, a
  strong coherence check.
* **Viewer number changes:** the merged set has **8,410 damaged footprints** of
  its own; harmonized onto the Overture base (the common comparison base, ~1.15×
  like every source), the viewer's Microsoft damaged count goes **~12,708 → 9,636**
  (the intended ~24% reduction from dedup + multi-observation reconciliation).
* No cloud / not-analysed layer: the valid-area mask is a simple AOI outline with
  no interior holes (confirmed across all masks), so — as before for Microsoft —
  the analysed area *is* the AOI. (Re-check for a future cloud-affected AOI.)
* Bad / open: if Microsoft later sends individual tiles outside this merged set,
  we must merge them in; the per-AOI path remains for that.
* **Residual cross-scene duplication (accepted):** the merged set is *mostly* but
  not fully deduplicated — ~3,800 buildings (~5–6% of the 72,162; ~1–2% of damaged)
  are the same building detected in overlapping satellite scenes whose per-scene
  footprints overlapped too little to merge. It is a Microsoft artifact (not
  Overture) and does not affect our Overture-based comparison base, so we accept it
  and flag it upstream. Quantified/verified in
  [`exploratory/0001-microsoft-overture-duplicates/`](../../exploratory/0001-microsoft-overture-duplicates/findings.md).

## More Information

The merged `.gpkg` (27 MB) repeatedly failed to upload: the Azure SDK sends blobs
≤ 64 MB as a single PUT, which stalls on a slow/flaky uplink. Fixed by uploading
in **staged 4 MB blocks** (`gie.blob.upload_parquet_staged`), now used across the
pipelines. Supersedes the per-AOI handling on the viewer; the per-AOI bronze is
retained.
