---
status: "accepted"
date: 2026-07-14
deciders: Zack
---

# LIST ResNet SAR damage source: lossless-COG bronze + class-2-only mapping

## Context and Problem Statement

LIST (a WFP collaboration with LIST and CERN) delivered two ~5.3 GB striped
Float32 GeoTIFFs (values `{0,1,2}`, 10 m, EPSG:32618) of per-building damage
predictions for the Venezuela earthquake, with **no methodology document** — the
model (ResNet, from the filename) and sensor (SAR, provider-stated) are inferred,
not documented. Landing this as a new source raised three non-obvious decisions:
what to store in bronze, how the `{0,1,2}` classes map to the damage model, and
how to plumb it through.

## Decision Drivers

* Reproducible ingestion; ability to *work from blob* (a stated goal).
* Don't misrepresent a preliminary screen as confirmed damage.
* Consistency with the existing medallion pipeline + `data_ledger.md`.
* Faithfulness to the delivered data (no silent value changes).

## Considered Options

Bronze payload: **(a) raw as-received Float32** · (b) lossless Byte COG · (c) both.
Class mapping: **(a) naive `1=Possibly, 2=Damaged`** · (b) class-2-only = Damaged.
Plumbing: **(a) Portolan catalog at bronze** · (b) medallion bronze loader.

## Decision Outcome

**Bronze = lossless Byte DEFLATE COG** (`gie.raster.to_byte_cog`, guarded to
refuse any non-integer/out-of-range value): the pixels are exactly `{0,1,2}`, so
Float32→Byte is bit-for-bit lossless; 5.3 GB → ~7 MB, a validated true COG that
is trivially streamable from blob. Raw-as-received (ADR-0005/0008 convention) was
**rejected** — a ~10.6 GB upload that defeats "work from blob"; the original zip
preserves the raw delivery externally, so "both" was unnecessary.

**Only class 2 → damage_class 2 (Damaged); 0 and 1 = analysed, not flagged.**
Validated against IMPACT-v2 and OSU: class 2 is ~9× enriched for cross-source
agreement (14% vs 1.5% background) and aligns with OSU (SAR). The naive mapping
was **rejected** on the data — class 1 covers **50% of all buildings** at
background-level agreement (~2.5%), i.e. built-up / generic change, not damage;
it would have injected ~2.5M false positives. Mirrors OSU's single-class approach
(~163K damaged).

**Medallion bronze loader** (mirrors the other ~8 sources). Portolan-at-bronze
was **rejected** — it would introduce a second cataloging system at ingestion
(Portolan is the serving tier per ADR-0011), off the ledger/harmonizer/`run_all`
flow, with less conversion control.

### Consequences

* Good — tiny cloud-native COG; honest, validated damage layer; consistent with
  the pipeline and ledger; generic raster primitives (`gie.raster`) reusable for
  the next raster source.
* Bad / caveats — bronze deviates from "as-received" (raw kept only in the
  delivery zip); class semantics are an **assumption pending provider docs**
  (reprocess trigger); **areal coverage omitted** (the extent is the raster's
  ocean-padded rectangle → would over-read; building-count coverage still flows);
  LIST is a broad screen with the **highest damaged count** of any source —
  driven by the **widest AOI**, not a higher rate (its ~3.3% damage fraction
  matches IMPACT ~3.4% / OSU ~2.5%).

## More Information

Live on staging (dev tier); not promoted to prod. The viewer methodology card
carries WFP's requested disclaimer ("methodology still under refinement…") and
attributes WFP-LIST-CERN. Reprocess `harmonize_list.py` if the provider
documents a different `{0,1,2}` taxonomy. Related: ADR-0005 (bronze idempotency),
ADR-0008/0015 (IMPACT SAR/vector), ADR-0009 (OSU), ADR-0018 (UH), ADR-0011
(Portolan serving). Load-performance impact is tracked in ADR-0021.
