---
status: "proposed"
date: 2026-08-05
deciders: Zack Arno
---

# GitHub Pages site with no build step, and passphrase gating by encryption

## Context and Problem Statement

The damage-product evaluation produced two artefacts worth sharing outside the team — a
reveal.js results deck and a technical manuscript, both rendered from Quarto in
`exploratory/paper/`. There was nowhere to put them. Rendered HTML is gitignored, figures are
gitignored globally (`figs/`), and rendering needs Azure blob credentials, so **CI cannot build
these documents and a fresh clone cannot either**; anything published must be rendered locally
and committed.

Both are pre-publication, so they need a passphrase. The repository and any GitHub Pages site
are **public**, which rules out the obvious implementation.

Two decisions are recorded together because the second constrains the first: whatever publishes
the site has to be able to publish ciphertext.

## Decision Drivers

* CI cannot render the artefacts, and must not need credentials to deploy them.
* A deploy must not be breakable by an unrelated dependency problem.
* Pre-publication documents must not be readable by anyone who finds the repo or the URL.
* A reader must be able to tell "I typed the wrong passphrase" from "the site is broken".
* Two artefacts, one author. Machinery has to be proportionate to that.

## Considered Options

* **Publishing**: `pages/` is the site, no build step — vs. porting the manifest-driven
  `assemble.py` from `ds-storm-impact-harmonisation` — vs. Quarto/MkDocs publishing the `.qmd`
  sources directly.
* **Gating**: build-time AES-GCM encryption decrypted client-side — vs. a published passphrase
  hash plus a CSS overlay (the `ds-geospatial-impact-exposure` pattern) — vs. server-side auth
  on Azure App Service.

## Decision Outcome

**Publishing: `pages/` is the site.** Its directory layout is the URL layout, so nothing is
copied, generated or assembled; `deploy-pages.yml` uploads the tree as-is. The workflow's shape
otherwise matches `ds-geospatial-impact-exposure`'s (artifact deploy, no `gh-pages` branch),
triggering on `v1` because that is this repo's trunk.

**Gating: build-time encryption.** `scripts/encrypt_page.py` gzips the rendered HTML and seals it
with AES-256-GCM under a PBKDF2-SHA256 key; what is committed is `content.enc`, ciphertext.
`pages/assets/gate.js` derives the key in the browser and replaces the document with the
decrypted artefact. Encryption runs locally and never in CI, so the deploy path holds no secret.

The two sites keep a shared **design language** — the HDX v2 tokens, Merriweather/Roboto and
particle hero are copied verbatim from `ds-storm-impact-harmonisation` — while sharing no build
machinery.

### Consequences

* Good, because CI has no build step, no dependencies and no credentials: the failure mode where
  a broken `uv sync` takes the whole site down cannot occur here.
* Good, because the protection does not depend on the repo staying private, and the AES-GCM tag
  *authenticates* the passphrase — there is no comparison to bypass.
* Good, because the iteration count travels in the file header, so it can be raised later
  without invalidating already-published files.
* Bad, because adding a product means editing the shared `pages/index.html`. With one author
  that is a six-line edit; at more contributors the manifest approach becomes the better trade.
* Bad, because ciphertext is incompressible, so every re-render commits a fresh ~4 MB blob that
  git cannot delta. Mitigated only by re-encrypting deliberately.
* Bad, because a gzip step means the gate needs `DecompressionStream` — Safari 16.4+, Firefox
  113+. It buys 6.24 MB → 3.90 MB on the deck. Failure is a thrown error, not a blank page.
* Neutral, because gating is per-artefact and all-or-nothing: there is no per-person access and
  no revocation short of re-encrypting. Adequate for "not ready to publish", not for
  "must never be seen by person X".

## Pros and Cons of the Options

### `pages/` is the site, no build step

* Good, because the deploy cannot fail for any reason other than GitHub being down.
* Good, because what you see in the repo is exactly what is served — no output tree to reason about.
* Bad, because the landing page is a shared file, so concurrent contributors would conflict.

### Port `assemble.py` and `page.toml` manifests

* Good, because products are discovered by globbing, so adding one touches no shared file and
  parallel branches merge cleanly.
* Good, because it validates manifests and fails loudly on collisions.
* Bad, because most of its 257 lines implement a **copy step** — resolving `source.dir`,
  `include` lists, path-traversal guards — that exists to pull in a dashboard **built elsewhere
  as a GitHub artifact**. Both of our artefacts are rendered locally and vendored at their final
  URL path, so there is nothing to copy and nothing to validate.
* Bad, because the no-conflict property it buys is worth little at one author and two products.

### Quarto/MkDocs publishing the `.qmd` sources

* Bad, because it cannot work: rendering needs figures that are gitignored and blob credentials
  that CI does not have. This is the constraint that forces vendoring rendered output.

### Published passphrase hash plus CSS overlay

* Good, because it is ~90 lines with no build step, and it is the existing pattern in
  `ds-geospatial-impact-exposure`.
* Bad, because it is cosmetic, as that implementation's own header comment states: the content
  ships to the browser before the prompt, the overlay is removable from devtools, and the hash
  being public makes a weak passphrase brute-forceable offline.
* Neutral, because it was the **right** choice there: that app fetches its data files separately
  at runtime, so encrypting the page would have protected nothing without encrypting every data
  file and rewriting the fetch layer. Our artefacts are single self-contained documents, so
  encryption costs one script.

### Server-side auth on Azure App Service

* Good, because it gives real per-person access control and revocation.
* Bad, because it splits the site across two hosts and two URLs for two documents, and adds
  hosting to maintain for a case study that will be published or abandoned within months.

## More Information

* `pages/README.md` — layout, the re-render/re-encrypt procedure, and an honest statement of what
  the gate protects against.
* Envelope format and the three distinguishable failure states: `pages/assets/decrypt.js`.
* Design discussion: `docs/superpowers/specs/2026-08-05-paper-pages-site-design.md`.
* Reference implementations: `OCHA-DAP/ds-storm-impact-harmonisation` (`pages/_build/`, its
  ADR-0003) and `OCHA-DAP/ds-geospatial-impact-exposure` (`web/auth.js`, `deploy-pages.yml`).
* **Revisit if** a third contributor starts adding products regularly (the manifest approach
  wins), or if any artefact needs per-person access or revocation (encryption does not provide
  it), or once the paper is published and the gate should simply be removed.
