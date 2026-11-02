---
status: "accepted"
date: 2026-11-02
deciders: Zack Arno
---

# Group the landing page into hubs that index pages in place, rather than moving directories

## Context and Problem Statement

The landing grid had grown to fourteen cards: seven Venezuela damage-evaluation artefacts in
several versions, three flood-label pages, two viewers, a tracker and the experimental hub. A
reader could not tell the current product from its predecessors, or one line of work from
another. ADR-0041 had just folded the Nepal pages under `/experimental/` by moving their
directories. Should the Venezuela and CEMS/UNOSAT work be grouped the same way?

## Decision Drivers

* One card per line of work on the landing page; versions and superseded items one level down.
* Several branches are mid-flight on the scroll story and the brief; the change must not touch
  anything they publish.
* The paper publish script writes to fixed paths (`slides/damage-evaluation/`, `manuscript/`,
  `brief/`); Hypothesis annotations anchor to the `/manuscript/` URL; reviewers hold links.
* The flood pages are pipeline outputs regenerated in place (`pipelines/cems_flood/report.py`,
  `pipelines/flood_labels/`).

## Considered Options

1. **Move directories under the hub**, as ADR-0041 did for the Nepal pages.
2. **Hub index pages that link to the existing top-level directories.**
3. Collapse groups into `<details>` blocks on the landing page itself.

## Decision Outcome

Chosen option 2. `pages/venezuela-2026/` and `pages/cems-unosat/` are plain index pages, each
with its own card grid, linking to the artefacts where they already live. `venezuela-2026/
archive/` lists superseded versions (story v1, story v2, the legacy single-event viewer) as
muted cards. The landing grid keeps one card per hub. Within the Venezuela hub the top level is
the shortlist to publicise (story v4, brief, multi-event viewer); everything that led there
(briefings, deck, write-up, earlier stories) sits in the archive. The grouped pages' own back
links point at the hub or archive that lists them; pipeline-generated pages keep theirs.

ADR-0041 moved directories because the point there was to put the plaintext behind a gate, and
those pages had nothing addressing their paths but their own build scripts. Neither holds here.

### Consequences

* Good: nothing in flight is touched; no URL any reviewer, script or annotation uses changes.
* Good: a hub card is one HTML block to add; retiring a superseded page is deleting a card.
* Bad: the URL structure no longer mirrors the grouping (`/manuscript/` sits beside
  `/venezuela-2026/` rather than under it). The README says so, and says why.
* Bad: the hub blurbs duplicate the artefacts' card text; a title change has to be made twice.

## Pros and Cons of the Options

### 1. Move directories

* Good: URL layout mirrors the grouping.
* Bad: breaks `publish_pages.sh` targets, the Hypothesis anchors, shared links, and the flood
  pipelines' output paths, and conflicts with every branch that republishes an artefact.

### 3. `<details>` blocks on the landing page

* Good: no new pages.
* Bad: everything stays on one page, so the grouping is visual only; the landing page remains
  long in source and in search results, and gated and plain items mix inside each block.
