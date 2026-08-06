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

**Does protect** against this repository being public, the site being public, a forwarded link,
and search indexing. Browsing the repo gets you ciphertext.

**Does not protect** against anyone who has the passphrase, or anyone they pass it to. There is
no per-person access and no revocation short of re-encrypting with a new passphrase. This is the
right tool for "not ready to publish"; it is not the right tool for "must never be seen by
person X". For that, use a host with server-side auth.

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

**The `group` is not optional in practice.** Without it, annotations land in Hypothesis's public
layer, where anyone can read them — on a document we went to the trouble of encrypting. Create a
private group, add the reviewers, and put its id above.

**Know what this discloses.** Annotations, including the passages they quote, are stored on
Hypothesis's servers, not ours. A private group controls who can *read* them; it does not keep
excerpts of a pre-publication manuscript inside our infrastructure. If that is not acceptable for
a given document, review it as a `.docx` instead (`quarto render manuscript_v2.qmd --to docx`) and
leave `comments` out.

**The deck cannot use this.** Quarto's `comments` is an HTML-format feature — its
`hypothesis.ejs` lives under `formats/html/` — and does not apply to `revealjs`. Comments on the
deck's content belong on the manuscript.

## What is deliberately not published

- `satellite_damage_evaluation_v1.qmd` — earlier deck whose numbers predate the corrections.
- `findings.qmd` — the internal running register, including negative and superseded results.
- `manuscript_draft.qmd` — superseded by `manuscript_v2`.

Publishing any of these would put retracted numbers in circulation. They have no page here on
purpose, rather than being published and marked deprecated.
