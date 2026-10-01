---
status: "accepted"
date: 2026-09-22
deciders: Zack Arno
---

# Silver/gold audit reads per-code summary tables, not the full corpus of raw silver layers

## Context and Problem Statement

`pipelines/unosat/audit.py` checks S3 (acquisition dates plausible) and S4
(vocabulary membership) need per-polygon columns — `acq_datetime`,
`acq_window_start/end`, `acq_precision`, `layer_kind`, `role`, `class_method`,
`acq_method` — that in full only exist in the raw silver layer files
(`unosat/silver/{observed_event,coverage}/code=*/layer=*.parquet`, one file
per distinct layer content). The silver working set is 7.6 GB across 410
zips of *source* archives (design doc, §Sizing); the per-polygon GeoParquet
silver produces from them is comparable in scale and grows with every future
harvest. Reading every layer file in the corpus for a single audit run,
every time the audit runs, does not scale with that corpus and duplicates
work gold's own build already does per code. How should the audit get the
columns S3 and S4 need without an unconditional full-corpus read?

## Decision Drivers

* The audit runs repeatedly (defect-fix loop: audit → reprocess stale codes
  → audit), so its own cost compounds; a full-corpus read on every pass is
  the expensive part of every iteration, not a one-time cost.
* Fail loudly: an omitted check must say so, not silently look identical to
  a pass (global constraints; see also the S4 attribution fix this ADR sits
  beside — a violation must still name its code or say plainly that it
  cannot).
* G2 (excluded-kind polygon accounting) has no substitute for the raw
  per-polygon `layer_kind` values — there is no aggregate table that already
  carries what it needs — so at least one check unavoidably wants full
  per-code reads, and it should not force every other check to pay the same
  cost.

## Considered Options

* **Full-corpus read**: for S3/S4, read every code's `observed_event`/
  `coverage` partition via `silver.iter_layer_files`/`read_layer_file`, as
  G2 or gold's own build does.
* **Per-code `sources`/ledger summaries (CHOSEN)**: S3's acquisition columns
  and part of S4's vocabulary (`acq_precision`) come from the small,
  already-deduplicated per-code `sources` table (`silver.sources_frame`,
  one row per `(code, sensor, acquisition)`); the rest of S4
  (`status`, `geometry_source`, `layer_kind`, `role`) comes from the
  processing ledger already loaded for S1/S2/S5-S7, including its
  `kind_counts_json` column, which already records which `layer_kind`/`role`
  values a layer's rows used without carrying the rows themselves.
* **No check**: drop S3/S4 from the audit rather than pay for the data they need.

## Decision Outcome

Chosen option: per-code summaries. S3's `acq_rows` and S4's `acq_precision`,
`status`, `geometry_source`, `layer_kind` and `role` are all derivable from
tables the audit already loads for other rules or that are cheap to fetch in
full (the `sources` table is one small file per code); none of that requires
opening a single raw geometry file. G2 is left reading real per-code silver
partitions (via `iter_layer_files`/`read_layer_file`), because there is no
cheaper substitute for it, but it is restricted to codes already cached in
the local silver mirror (checked with a blob LIST, never a download) — a
gold code not yet mirrored locally is named and skipped rather than
triggering the exact full-corpus read this ADR avoids for every other rule.

### Consequences

* Good: S3/S4 (except G2's corpus-sized read) cost roughly what S1/S2/S5-S7
  already cost — no new full-corpus network or parse time added by this
  audit.
* Good: the audit's own cost no longer scales with corpus growth for every
  rule but one, so it stays cheap enough to run every iteration of the
  defect-fix loop.
* Bad: **S4 does not check `class_method` or `acq_method`.** Both are
  per-polygon-only columns with no aggregate table standing in for them; a
  vocabulary violation in either would only be caught by a full silver read
  (or by gold/silver's own construction-time validation, which is a
  different, narrower guarantee than an independent audit). This is printed
  every silver run (`VOCAB_NOTE` in `pipelines/unosat/audit.py`) so the gap
  is visible, not silent.
* Bad: G2 audits a shrinking-over-time subset of gold codes on any work dir
  that has not locally mirrored the whole silver corpus (e.g. right after a
  fresh `gold.py` run against blob-only silver output). The CLI prints the
  checked/skipped ratio mid-run and, when the run as a whole passes, on the
  final summary line, so a green run is never mistaken for a full one.

## Pros and Cons of the Options

### Full-corpus read

* Good: every S3/S4 column, including `class_method`/`acq_method`, is
  checked with no gaps.
* Bad: cost scales with the whole corpus (7.6+ GB of source zips, and their
  parsed layer output) on every audit run, including runs during the
  defect-fix loop that only need to re-check a handful of codes.

### Per-code summaries (chosen)

* Good: cheap, reuses data already loaded for other rules.
* Neutral: leaves G2 as the one rule that still pays the full per-code cost,
  scoped to what is already local.
* Bad: two columns go unchecked by this audit (see Consequences).

### No check

* Good: no cost at all.
* Bad: S3/S4 catch real defects (an acquisition date decades off, a
  vocabulary value silver should never emit); dropping them trades a
  correctness guarantee for a cost the per-code option avoids anyway.

## More Information

Revisit if `class_method`/`acq_method` need auditing without a full read: the
natural fix is to add their distinct values to `kind_counts_json` (or a
sibling summary column) at silver-build time, the same way `layer_kind`/
`role` are already carried, rather than reading raw geometry for it.
