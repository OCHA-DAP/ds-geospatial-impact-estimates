---
status: "accepted"
date: 2026-10-30
deciders: Zack Arno
---

# Gate experimental pages behind their own passphrase, under /experimental/

## Context and Problem Statement

The Nepal glacier-collapse work (SAR precursor report, Langtang and central-Himalaya facet
watches; `exploratory/0005-nepal-glof-sar-precursor/`) was published as three plain pages at
the top of the landing grid. It is exploratory: the method is still being tested and the pages
rank faces against their own history rather than predicting anything. Shown that prominently,
next to the reviewed damage-evaluation artefacts, it reads as a product. How do we keep the
pages reachable for the people who should see them while making clear they are experiments,
and stop them being stumbled into or forwarded?

## Decision Drivers

* The landing page should present the damage-evaluation line; experimental work must read as
  an aside.
* The repository and the site are public, so a hiding mechanism must actually hide (the
  pages README already rejects a JavaScript prompt in front of plaintext as cosmetic).
* The audience for the Nepal work is not the audience holding the damage-evaluation
  passphrase (external reviewers hold that one).
* The Nepal pages are build outputs rebuilt on new data; the publish path must survive that.

## Considered Options

1. **Demote only**: one "Experimental" card linking to a plain hub page; Nepal pages stay
   plaintext at their URLs.
2. **Gate the hub page only**: as 1, with a passphrase form on the hub.
3. **Encrypt the hub and all three Nepal pages, own passphrase, under `/experimental/`.**
4. **Encrypt with the shared damage-evaluation passphrase.**

## Decision Outcome

Chosen option 3. The landing grid ends with one muted "Experimental analyses" card. It leads to
`pages/experimental/`, a gate page whose decrypted content is a small index of the Nepal pages,
each of which is itself a gate page plus `content.enc` under `pages/experimental/<name>/`. All
four are encrypted with `scripts/encrypt_page.py` under a separate experimental passphrase
(`GIE_PAGE_PASS_EXPERIMENTAL`, else `~/.gie-page-passphrase-experimental`), driven by
`scripts/publish_experimental.sh`. The gate caches the passphrase for the browser tab, so a
reader enters it once at the hub.

The three build scripts no longer write into `pages/`. They write the finished page document
to the gitignored `data/<name>.page.html`, which is the encrypt input. `pages/` never holds the
Nepal plaintext again; earlier copies remain in git history.

### Consequences

* Good: the pages are not discoverable from the site or the repo without the passphrase, and
  they are visibly labelled experimental where they are listed.
* Good: sharing the Nepal work does not share the damage-evaluation artefacts, or vice versa.
* Bad: the old top-level URLs (`/langtang-sar-precursors/` etc.) no longer exist; links already
  shared break. Accepted: the point is to stop those links circulating.
* Bad: a dashboard rebuild is now two steps (build, then publish). Each build script prints
  the publish command; the README states the rule.
* Bad: `gate.js` caches one passphrase per tab, so a reader who opens a Nepal page and then a
  damage-evaluation page re-enters the latter's passphrase. Accepted rather than changing a
  shared asset for a rare path.

## Pros and Cons of the Options

### 1. Demote only

* Good: smallest change, no build-script edits.
* Bad: anyone with a URL, or browsing GitHub, reads the pages; "experimental" is a label, not a
  boundary.

### 2. Gate the hub only

* Bad: protects nothing. The pages stay plaintext at public URLs, and the hub's own links
  would be readable in the repo. The pages README rejects exactly this.

### 4. Encrypt with the shared passphrase

* Good: one passphrase for readers.
* Bad: the shared passphrase is already with external reviewers of the paper, so it would hide
  the Nepal work from the public but not from the people most likely to mistake it for a
  finding.
