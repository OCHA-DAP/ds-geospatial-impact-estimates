# Design: GitHub Pages site for the paper artefacts

Date: 2026-08-05
Branch: `paper-pages` (worktree `../gie-paper-pages`, branched from `paper-evaluation`)
Status: awaiting review

## Context

The VE earthquake damage-product evaluation has produced two artefacts worth sharing outside
the team: a reveal.js results deck and a technical manuscript, both rendered from Quarto in
`exploratory/paper/`. There is nowhere to put them. Rendered HTML is deliberately gitignored
(`exploratory/paper/*.html`), figures are gitignored globally (`figs/`), and rendering needs
Azure blob credentials — so CI cannot build these documents, and a fresh clone cannot either.

An earlier uncommitted attempt (`web-paper/` plus `deploy-paper-pages.yml`) hardcoded a single
product, carried stale copy, and wrapped the deck in a plaintext-password prompt that protects
nothing on a public repo. It is replaced, not extended.

The goal: one GitHub Pages site that is the repo's publishing surface — the two paper artefacts
now, room for later work, and a link out to the existing impact viewer — with genuine
passphrase protection on the two pre-publication documents.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Worktree `../gie-paper-pages`, branch `paper-pages` off `paper-evaluation` | A concurrent session owns `exploratory/paper/**` and `docs/decisions/**` on `paper-evaluation`. Branching from it (not `v1`) means this branch already contains the paper sources, so the merge back is a fast-forward of disjoint files. |
| 2 | `pages/` **is** the deployed site — no assemble step | Directory layout equals URL layout, so nothing is copied or generated. CI runs no Python and installs no dependencies. |
| 3 | Products: gated deck, gated manuscript, open external viewer link | The v1 deck and `findings.qmd` are **not** published (superseded numbers; internal register of negative results). |
| 4 | Repo-wide framing, not paper-specific | The site is titled for the repo's impact-estimate work; the paper artefacts are its first products. Adding later work does not mean rewriting the hero. |
| 5 | Gating by **build-time AES-GCM encryption**, decrypted client-side | The repo is public, so a JS prompt in front of plaintext HTML is a false assurance. Committing ciphertext means the protection survives the repo being public. |
| 6 | gzip before encrypting | Measured on the real deck: 6.24 MB → 3.90 MB. |

### Why not port the reference repo's architecture

`OCHA-DAP/ds-storm-impact-harmonisation` discovers products by globbing
`pages/products/*/page.toml` and copying each product's files into an output tree
(`pages/_build/assemble.py`, 257 lines). That machinery earns its keep there because one
product is a **dashboard built elsewhere** — a GitHub build artifact that has to be pulled into
the site, plus a database export in the same job. Neither applies here: both artefacts are
rendered locally by one person and vendored at their final URL path, so there is no source
directory to resolve, nothing to copy, and no `include`/path-traversal validation to do.

Porting it would also inherit a known wart their own ADR records: the data export shares the
deploy job, and when `uv sync --frozen` broke on 2026-08-04 the whole site stopped deploying
over an unrelated dependency problem.

What is worth keeping from that repo is its **design language**, which we copy exactly (HDX v2
tokens, Merriweather/Roboto, particle-network hero, card grid), so the two sites read as one
system.

## Layout

```
pages/                                  uploaded verbatim; this tree IS the site
  index.html                            landing page — hero + three cards, hand-written
  README.md                             how to add a page, re-render, and re-encrypt
  assets/
    site.css                            HDX v2 tokens, cards, chips, gate form
    hero.js                             particle-network canvas
    gate.js                             fetch → derive key → decrypt → gunzip → render
  slides/damage-evaluation/
    index.html                          gate shell   (→ /slides/damage-evaluation/)
    content.enc                         ciphertext of satellite_damage_evaluation_v2.html
  manuscript/
    index.html                          gate shell   (→ /manuscript/)
    content.enc                         ciphertext of manuscript_v2.html

scripts/encrypt_page.py                 local-only encryptor; deliberately OUTSIDE pages/
.github/workflows/deploy-pages.yml      checkout → upload pages/ → deploy
docs/decisions/00NN-*.md                ADR recording decisions 2 and 5
```

`web-paper/` and `.github/workflows/deploy-paper-pages.yml` are superseded. Both are untracked
in the main working tree, so this branch simply never contains them; the stale copies need
deleting from that tree by hand.

Adding a fourth product later = create a directory with an `index.html`, add a ~6-line card to
`pages/index.html`. That shared-file edit is the accepted cost of having no build step.

## The gate

### File format (`content.enc`)

| offset | bytes | field |
|---|---|---|
| 0 | 8 | magic `GIEENC01` |
| 8 | 16 | PBKDF2 salt |
| 24 | 12 | AES-GCM nonce |
| 36 | 4 | PBKDF2 iteration count, uint32 big-endian |
| 40 | … | AES-GCM ciphertext with 16-byte tag appended (WebCrypto's layout) |

Plaintext is the gzipped UTF-8 bytes of the rendered HTML. **Iterations live in the header**
rather than as a constant duplicated in both the Python and the JS, so the cost can be raised
later without invalidating already-committed files or risking a silent mismatch.

### Encrypting (local, manual)

```bash
uv run --with cryptography python scripts/encrypt_page.py \
  --in  exploratory/paper/satellite_damage_evaluation_v2.html \
  --out pages/slides/damage-evaluation/content.enc
```

Passphrase from `$GIE_PAGE_PASS` if set, otherwise a `getpass` prompt — two explicit paths, no
default and no fallback. Missing input is an error, not a silent skip. Defaults to 600,000
PBKDF2-SHA256 iterations (OWASP guidance). Needs `cryptography`; AES-GCM is not in the stdlib,
and this script never runs in CI, so the dependency costs nothing there.

### Decrypting (`gate.js`)

PBKDF2-SHA256 → 256-bit AES-GCM key → decrypt → `DecompressionStream('gzip')` → replace the
document via `document.open()`/`write()`/`close()`.

Whole-document replacement rather than an iframe: the deck is a complete HTML document with its
own `<head>` and scripts, and reveal.js keyboard handling and fullscreen behave badly when
framed.

Three **distinguishable** failure states, per the repo's fail-loudly rule — a reader must never
be unable to tell "wrong passphrase" from "the site is broken":

| condition | message |
|---|---|
| `fetch` not ok / network error | "Could not load the encrypted content (HTTP _n_)." — a site fault |
| magic bytes wrong | "This file is not a recognised encrypted page." — a build fault |
| AES-GCM tag fails | "Wrong passphrase." — the only user-correctable one |

The GCM tag *authenticates* the passphrase; there is no string comparison to bypass. Gate pages
carry `<meta name="robots" content="noindex">`. No passphrase caching across pages — two pages,
one prompt each.

### What this does and does not protect

It protects against: the repo being public, the site being public, a forwarded link, search
indexing. It does not protect against: passphrase sharing, or anyone who has ever been given
it. `pages/README.md` will say exactly this — the previous attempt's honesty about its own
limits is the one thing worth keeping from it.

The passphrase is not committed anywhere. It needs recording wherever the team keeps shared
credentials.

## Landing page

Single centred `.wrap` (max 1080px, white on `--n05`, soft shadow), three zones, lifted from
the reference template:

1. **Hero** — `--b6` panel, animated particle-network canvas behind it (particle count
   `clamp(22, W·H/7000, 80)`, links under 120px, DPR-aware, one static frame under
   `prefers-reduced-motion`). Eyebrow "OCHA CENTRE FOR HUMANITARIAN DATA", serif `<h1>`
   "Geospatial Impact Estimates", one paragraph capped at 64ch.
2. **Cards** — uppercase micro-label, `repeat(auto-fill, minmax(300px, 1fr))` grid, gap 16px.
   Each card a whole `<a>`: serif title + chip, blurb, top-bordered foot showing the route.
3. **Footer** — tinted call-out pointing at `pages/README.md`.

Tokens copied verbatim: `--b5 #269777` `--b6 #1e795f` `--b7 #18614c` `--b05 #e9f5f1`
`--b1 #d4eae4` `--n9 #1f2324` `--n8 #3f4748` `--n7 #5e6a6b` `--n05 #f5f7f7`. Merriweather 700
for `h1`/card titles, Roboto 400/500/700 elsewhere. Light mode only, matching the reference —
the one media query besides the 640px breakpoint is `prefers-reduced-motion`.

New this repo: a **`chip-gate`** ("Passphrase") variant alongside the reference's `chip-ext`,
styled from the same tokens. Every card states its access up front, so nobody hits an
unexplained prompt.

Cards:

| card | route | chip | blurb source |
|---|---|---|---|
| Satellite damage product evaluation | `/slides/damage-evaluation/` | Passphrase | 19-slide results deck; six products, one event |
| Damage evaluation — technical write-up | `/manuscript/` | Passphrase | the manuscript |
| Geospatial impact viewer | external | External | the deployed viewer app |

Framing copy must not overstate a single-event case study as a general verdict on these
products, and must state the 2026-07-15 data snapshot.

## Deploy

`.github/workflows/deploy-pages.yml` — `actions/checkout` → `configure-pages` →
`upload-pages-artifact` (path `pages`) → `deploy-pages`. Trigger: push to `v1` on paths
`pages/**` and the workflow file, plus `workflow_dispatch`. No build step, no credentials, no
data export. `pages/**` cannot collide with `swa-deploy.yml`'s `web/**` filter.

## Verification — results

Run against the real artefacts (deck 6.34 MB, manuscript 4.01 MB) with a throwaway passphrase.

**Verified.**

| what | how | result |
|---|---|---|
| Envelope round-trip, byte-exact | `encrypt_page.py` self-check, plus a Node harness importing `decrypt.js` | 6.24 MB in, identical out; 163 ms |
| The four failure kinds are distinguishable | Node harness: wrong passphrase, garbage file, truncated file, flipped ciphertext byte | `passphrase` / `malformed` / `malformed` / `passphrase` |
| `encrypt_page.py` refuses to guess | no `GIE_PAGE_PASS` and no tty; nonexistent `--out` directory | exit 1, message names the cause |
| Decryption in a real browser | Chrome, `decrypt.js` over HTTP | deck 3.98→6.34 MB in 100 ms; manuscript 2.28→4.01 MB in 86 ms |
| **Full gate path end to end** | Chrome via CDP, passphrase seeded, real gate page | manuscript decrypts and renders complete with TOC — screenshot captured |
| Stale cached passphrase self-clears | Chrome, `sessionStorage` seeded with a wrong value | form offered with **no** error text, cache dropped, no retry loop |
| Landing page, desktop and 375 px | Chrome screenshots | hero, cards, chips correct; single column and no horizontal overflow on mobile |

**Not verified — needs a human.** The **deck** decrypting is confirmed (its own inline `data:`
assets are fetched by the browser after `document.write`), but no rendered screenshot could be
captured: reveal.js's `requestAnimationFrame` loop prevents headless Chrome's compositor from
settling, so `Page.captureScreenshot` and `Runtime.evaluate` both hang — with `fromSurface:
false` too. The manuscript exercises the identical code path and renders fully. **Someone should
open the deck in a real browser once and click through a few slides.**

Also unverified: `prefers-reduced-motion` painting a single static frame (inherited unchanged
from the reference implementation).

### A bug this found

`gate.js` originally fetched with `cache: "force-cache"`, to avoid refetching several MB on a
return visit. In Chrome this **hung indefinitely** when the entry was already in the HTTP cache —
no network request, no resolve, no reject, so the gate sat on "Opening…" forever. Removed; the
default cache mode with ordinary ETag revalidation is what we want, and GitHub Pages sends the
headers for it.

Worth recording that removing it did **not** fix the symptom I was chasing at the time — that
turned out to be my iframe-based test harness, not the product. The cache-mode hang was real and
separate, and only a CDP trace distinguished them.

## Open items

1. **Publish the real ciphertext.** No `content.enc` is committed. The test files were encrypted
   with a throwaway passphrase and deleted, so the two gated routes 404 until someone runs
   `encrypt_page.py` with the real passphrase. Before doing that, confirm with the analysis
   session that the deck's two regenerated figures have landed — the render on disk is dated
   after that work started but has not been checked.
2. **GitHub Pages is not enabled** on `OCHA-DAP/ds-geospatial-impact-estimates`
   (`gh api .../pages` → 404). Repo admin must set Settings → Pages → Source: GitHub Actions.
   Nothing deploys until then, and deploying from `paper-pages` before merge additionally
   requires the `github-pages` environment to permit non-default branches.
3. **ADR number.** The concurrent session also writes to `docs/decisions/`; 0025 is the highest
   committed, so this ADR wants 0026 — needs confirming that session is not also claiming it.
4. **Repo weight.** Ciphertext is incompressible, so git stores a full ~3.9 MB blob per
   re-render of each artefact with no delta. Accepted; re-render deliberately, not habitually.
5. **`DecompressionStream`** requires Safari 16.4+ / Firefox 113+. Failure is a thrown error,
   not a blank page. Drop the gzip step if that floor is a problem.
6. **Hypothesis annotation needs a change inside the other session's boundary.** The
   `comments: hypothesis:` block goes in `manuscript_v2.qmd`, which this branch does not own —
   relay it rather than editing. Needs a private Hypothesis group created first, and a decision
   on whether storing quoted excerpts of a pre-publication manuscript on Hypothesis's servers is
   acceptable. `pages/README.md` documents both. Applies to the manuscript only; Quarto's
   `comments` does not support `revealjs`.
