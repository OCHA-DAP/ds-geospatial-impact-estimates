# Native vs Overture-snapped damage counts — the footprint-granularity gap

> **Status:** complete & verified (2026-07-03).
> **Verdict: snapping a source's damage onto the Overture base changes its building
> count, by an amount that scales with footprint granularity** — ~0 for point/coarse
> sources, large for fine polygon sources. It is a counting artifact, **not** missing
> or extra damage.
> Analysis: [`analysis.py`](analysis.py) · Feeds [ADR-0017](../../docs/decisions/0017-source-counts-two-bases-snapped-vs-native.md).

## Question

`harmonize_common` projects every source's damage onto the shared **Overture base**
(nearest footprint within `SNAP_M = 20 m`) so all sources are compared on one
basis. But a source's own **native** building count and its count of **distinct
Overture buildings flagged** are not the same number. How big is that gap, what
causes it, and — for UNEP debris especially (native 96,046) — which number do we
report?

## Data

Read from the immutable silver/bronze snapshots (see [ADR-0005](../../docs/decisions/0005-idempotent-versioned-bronze-ingestion.md)):

- **Overture base** — `silver/source=overture/adm0=VE/` (12 state regions, **5,257,092
  unique buildings**; `id` + geometry).
- **Microsoft** — `silver/source=microsoft/adm0=VE/footprints.parquet`, `damaged == 1`
  → **8,410** (footprints, ~Overture granularity).
- **CEMS** — `silver/source=copernicus_ems/adm0=VE/builtup_damage.parquet`, latest
  per-building points → **3,072**.
- **UNEP debris** — `bronze/source=unep_debris/adm0=VE/debris_buildings.gpkg` →
  **96,046** (Global Building Atlas polygons, fine).

## Method

Reproject all to EPSG:32619; snap each source's building/point centroid to the
nearest Overture centroid within 20 m; count **distinct** Overture buildings hit.
`native − distinct` splits into **collapse** (≥2 source buildings onto one Overture
building) and **dropped** (no Overture within 20 m). Sensitivity checked at 30/50 m.

**Cache-integrity guard (the reason this file exists in its current form).** The
Overture base is cached to `/tmp/gie_base_local`. An *earlier* run of this analysis
`glob`-ed a **half-built** cache (only the 6 western/inland regions; the coastal
states where the damage is were missing) and silently returned **69** distinct
Overture buildings for debris — a completely false number, caught only because it
contradicted a known fact (debris ≈ MS ≈ Overture to ~3 m). The corrected
`analysis.py` **reconciles the cache against blob and asserts local == blob per
region before reading**, and writes downloads atomically (temp + rename) so an
interrupted pull can't leave a truncated file that looks complete. Rule:
**reconcile-before-read; a partial cache must fail loud, never yield a subset.**

## Findings

Native vs Overture-snapped (20 m) damaged-building counts:

| Source | Footprint | Native | Snapped (distinct Overture) | Collapse | Dropped | Gap |
|---|---|---|---|---|---|---|
| Microsoft | footprints ≈ Overture | 8,410 | 8,342 | 68 | 0 | **−1%** |
| CEMS | per-building points | 3,072 | 2,708 | 283 | 81 | **−12%** |
| UNEP debris | GBA polygons (fine) | 96,046 | 75,656 | 18,917 | 1,473 | **−21%** |

**The gap is collapse, not coverage.** For debris, **98%** of buildings *do* find an
Overture building within 20 m (only 1,473 dropped) — Overture covers the debris area
fine. The −21% comes almost entirely from **~18,900 GBA footprints collapsing onto a
shared Overture building**: GBA is *finer* than Overture, so several GBA footprints
map to one Overture footprint. Loosening the snap to 30/50 m barely moves it
(75,656 → 76,193 → 76,369), so it is genuine granularity, not a too-tight match.

**The gap scales with footprint granularity vs Overture.** Point sources (CEMS) and
coarse footprints (Microsoft, itself ~Overture-derived) barely collapse; fine
polygon sources (GBA) collapse a lot. So the divergence is predictable from the
source's footprint model, and debris shows it most because GBA is the finest.

## What it feeds

[**ADR-0017**](../../docs/decisions/0017-source-counts-two-bases-snapped-vs-native.md) —
*compare on the Overture base, attribute on the native base.* Comparison contexts
(agreement view, cross-source counts) use the snapped count; attribution contexts
(native view, source headline, export) use the native authoritative count; the
UNEP debris hover shows both — `Damaged buildings: {native} (Overture-snapped:
{snapped})` — so the distinction is never lost. The gap being a granularity artifact
(not missing damage), and there being **no damage fraction** for debris (no analysed
extent — no denominator to amplify it), is what keeps the stakes low enough for a
dual-number convention rather than forcing one basis.
