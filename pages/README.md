# Pages site

**Live:** https://ocha-dap.github.io/ds-geospatial-impact-estimates/

`pages/` **is** the site. The directory layout is the URL layout, so there is no build step and
nothing is generated: `.github/workflows/deploy-pages.yml` uploads this tree as-is on push to
`v1`. No Python, no dependencies, no credentials in the deploy path.

```
pages/
  index.html                      landing page — hero and cards
  assets/site.css                 HDX v2 tokens, cards, gate form
  assets/hero.js                  particle-network hero canvas
  assets/decrypt.js               envelope parsing + AES-GCM/PBKDF2 (pure, no DOM)
  assets/gate.js                  the passphrase form
  slides/damage-evaluation/       -> /slides/damage-evaluation/
  manuscript/                     -> /manuscript/
```

## Adding a page

Create a directory with an `index.html`, then add a card to `index.html` — copy an existing
`<a class="k">` block and change the href, title, blurb and foot. Chips are optional:
`chip-ext` for something hosted elsewhere, `chip-gate` for a passphrase-gated page.

That shared edit to `index.html` is the deliberate trade-off for having no build system. The
sibling repo `ds-storm-impact-harmonisation` discovers products by globbing `page.toml`
manifests instead, which avoids the shared edit — worth revisiting if this site ever grows
enough contributors for that to matter. See ADR-0026.

## Checking locally

```bash
python3 -m http.server -d pages 8000
```

**Use a server, not `file://`** — WebCrypto only works in a secure context, so the gated pages
cannot decrypt from the filesystem.

## The gated pages

`slides/damage-evaluation/` and `manuscript/` do not contain their artefact. They contain
`content.enc`: the rendered document, gzipped and AES-GCM encrypted. The passphrase form derives
the key with PBKDF2-SHA256 and decrypts in the browser, then the decrypted document replaces the
gate page.

### What this protects, and what it does not

**Read this before assuming the gate makes anything confidential. It does not.**

`exploratory/paper/manuscript_v2.qmd` and `satellite_damage_evaluation_v2.qmd` are **tracked in
this public repository**. Anyone who finds them reads the prose, the numbers and the conclusions,
with no passphrase involved. That is a deliberate choice — the sources are fine being public.

So what the gate protects is the **publication surface**, not the findings:

- **Does protect:** nobody can forward a link to a finished, citable-looking deck or manuscript;
  search engines cannot index them; the polished artefact is not casually shareable before it is
  ready to be. Browsing the repo gets you `content.enc`, which is ciphertext.
- **Does not protect:** the findings themselves, which sit in the `.qmd` next door. Nor against
  anyone who has the passphrase or is given it. There is no per-person access and no revocation
  short of re-encrypting.

It is the right tool for "not ready to *present*". It is the wrong tool for "these numbers must
not get out" — that would additionally require the sources to stop being public, which is a
separate decision from this one. For per-person access, use a host with server-side auth.

Note the difference from `OCHA-DAP/ds-geospatial-impact-exposure`, which gates with a published
SHA-256 hash and a CSS overlay — cosmetic by its own admission, and correctly so: that app
fetches its data files separately at runtime, so encrypting the page would protect nothing.
These artefacts are single self-contained documents, which is why real encryption is cheap here.

### Re-publishing after a re-render

The passphrase is not in this repository. It lives wherever the team keeps shared credentials.

```bash
# 1. Re-render the artefact (needs the notebook stack — see exploratory/paper/README.md)
cd exploratory/paper
uv run --group etl --with nbformat --with nbclient --with ipykernel \
       --with matplotlib --with numpy --with shapely bash -c \
  'QUARTO_PYTHON="$(python -c "import sys; print(sys.executable)")" \
   quarto render satellite_damage_evaluation_v2.qmd --to revealjs'

# 2. Encrypt it into place (prompts for the passphrase, twice, unless $GIE_PAGE_PASS is set)
cd ../..
uv run --with cryptography python scripts/encrypt_page.py \
  --in  exploratory/paper/satellite_damage_evaluation_v2.html \
  --out pages/slides/damage-evaluation/content.enc

# 3. Commit and push to v1 — that fires the deploy
```

The manuscript is the same with `manuscript_v2.html` → `pages/manuscript/content.enc`.

`encrypt_page.py` round-trips its own output before writing, so a format or parameter bug fails
there rather than leaving a reader with an unopenable page. It refuses to run without a
passphrase and never invents one.

**Each re-render commits a fresh ~4 MB blob** that git cannot delta, because ciphertext is
incompressible. Re-encrypt deliberately, not on every small edit.

### Rotating the passphrase

Re-run step 2 for both artefacts with the new passphrase and commit. Readers with the old one
get "Wrong passphrase". Cached passphrases live in `sessionStorage` and are dropped
automatically when they stop working, so no one gets stuck on a stale value.

## Review and annotation

Reviewers comment on the **manuscript** with [Hypothesis](https://web.hypothes.is/), which
anchors threaded annotations to selected text. Quarto supports it natively, so this is YAML in
`manuscript_v2.qmd` rather than anything in this directory:

```yaml
format:
  html:
    comments:
      hypothesis:
        openSidebar: false
        showHighlights: whenSidebarOpen
        group: <private-group-id>      # omit and annotations go to the PUBLIC layer
```

Then re-render and re-encrypt as above. The client loads inside the decrypted document, and
because `document.write` leaves the URL unchanged, annotations anchor to `/manuscript/` stably
across re-publishes.

**The `group` is not optional, and the reason is the reviewers, not the manuscript.** Without it
annotations land in Hypothesis's public layer, readable by anyone.

Be precise about what is at stake, because it is easy to get backwards. The manuscript text is
**already public** in `manuscript_v2.qmd`, so Hypothesis quoting a passage discloses nothing new.
What would be newly public is the **reviewers' own commentary** — candid critique of the method,
of how hard a named provider gets criticised, of which flags are still open. That is the thing a
public annotation layer would expose, and it is why a private group is required.

Annotations are stored on Hypothesis's servers either way. A private group controls who can read
them; it does not put them inside our infrastructure. If a given review needs to stay entirely
in-house, do it as a `.docx` (`quarto render manuscript_v2.qmd --to docx`) and leave `comments`
out.

**The deck cannot use this.** Quarto's `comments` is an HTML-format feature — its
`hypothesis.ejs` lives under `formats/html/` — and does not apply to `revealjs`. Comments on the
deck's content belong on the manuscript.

## What is deliberately not published

- `satellite_damage_evaluation_v1.qmd` — earlier deck whose numbers predate the corrections.
- `findings.qmd` — the internal running register, including negative and superseded results.
- `manuscript_draft.qmd` — superseded by `manuscript_v2`.

Publishing any of these would put retracted numbers in circulation. They have no page here on
purpose, rather than being published and marked deprecated.
