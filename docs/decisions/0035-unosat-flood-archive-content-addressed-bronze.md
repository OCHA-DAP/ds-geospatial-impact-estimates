---
status: "accepted"
date: 2026-09-18
deciders: Zack Arno
---

# UNOSAT archive: content-addressed bronze from the HDX catalogue, SHP and GDB both archived, GDB authoritative

## Context and Problem Statement

The flood-fusion work needs analyst-made flood and water extents outside
Europe. UNOSAT publishes ~1,465 datasets on HDX, but HDX is only the
catalogue: bytes sit on five UNOSAT/CERN hosts, datasets are cumulative
snapshots that re-ship the same zip dozens of times (515 of 1,516 zips are
content-identical to another), and older layers store coded attributes whose
meaning lives only in the geodatabase's domain tables. How do we archive this
so nothing is lost, nothing is duplicated, and the codes stay decodable?

## Decision Drivers

* Upstream loses data (19 stable 404s, 6 HTML-as-zip) and has no SLA.
* Duplication is structural, not incidental.
* 2014–2021 attributes are integer codes bound to per-layer domains.
* One reader in `ds-flood-gfm` must serve CEMS and UNOSAT labels alike.

## Considered Options

* Bronze keyed by HDX dataset/resource (mirrors the catalogue; stores each
  identical zip up to 41 times).
* Bronze keyed by event code (like CEMS `code=`; UNOSAT resource names are
  not always parseable and one zip carries several attribute event codes).
* **Bronze keyed by sha256, ledger rows pointing at content (CHOSEN).**
* Archive SHP only (smaller; loses domains and 55 GDB-only feature classes in
  one event) vs SHP + GDB (CHOSEN).

* Local cache for silver: `pooch` (static registry of names+hashes; our
  ledger already is the registry) vs `fsspec` `filecache::` (keyed by URL;
  redundant once paths are content-addressed) vs DVC (a second
  content-addressed store beside the ledger) vs **a plain mirror of the
  bronze layout under `platformdirs` (CHOSEN)** — content addressing makes
  the cache never stale, so no library is needed.

## Decision Outcome

Content-addressed bronze (`blob={sha256}/{basename}`) with a resource-version
ledger; both SHP and GDB archived; silver reads the GDB first because it is
a superset with typed, domain-bound attributes and is authoritative where
exports disagree. Discovery uses `hdx-python-api` read-only. Terminal
upstream states are ledger statuses, never retries.

### Consequences

* Good: identical content stored once; the ledger, not the blob path, carries
  HDX identity; domains survive; resume and audit are exact.
* Good: the content-addressed layout makes duplicate-content races benign —
  two workers uploading the same bytes concurrently converge on the same
  blob path, so a lost upload race is recorded as `uploaded_dedup`, not a
  failure.
* Bad: a blob path says nothing human-readable about its content (the ledger
  is required to navigate); two formats of the same product are kept.
