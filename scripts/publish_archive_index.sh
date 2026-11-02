#!/usr/bin/env bash
#
# Encrypt the Venezuela archive index into pages/venezuela-earthquake-2026/archive/content.enc.
#
#   ./scripts/publish_archive_index.sh
#
# The archive listing is gated (it names and links every pre-publication artefact), so its
# source cannot live under pages/ — everything there deploys. The source is
# pages-src/venezuela-earthquake-2026/archive.html; edit it, run this, commit the ciphertext.
#
# Passphrase: the SHARED one (GIE_PAGE_PASS, else ~/.gie-page-passphrase) — the same passphrase
# the archived decks, write-up and earlier stories use, so a reader who opens the index does not
# meet a second prompt on the pages it lists. Not the brief's and not the experimental one.
#
# Encrypt only. No render, no commit, no push: merging to v1 is what publishes.

set -euo pipefail

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
SRC="$REPO_ROOT/pages-src/venezuela-earthquake-2026/archive.html"
OUT="${GIE_PAGES_DIR:-$REPO_ROOT/pages}/venezuela-earthquake-2026/archive/content.enc"
ENCRYPT="$REPO_ROOT/scripts/encrypt_page.py"

[[ -f $SRC ]] || die "source not found: $SRC"
[[ -d $(dirname "$OUT") ]] || die "output directory missing: $(dirname "$OUT")"
[[ -f $ENCRYPT ]] || die "missing $ENCRYPT"

if [[ -z ${GIE_PAGE_PASS:-} ]] && [[ -r $HOME/.gie-page-passphrase ]]; then
  GIE_PAGE_PASS="$(< "$HOME/.gie-page-passphrase")"
  export GIE_PAGE_PASS
  echo "passphrase: read from ~/.gie-page-passphrase (shared)"
elif [[ -n ${GIE_PAGE_PASS:-} ]]; then
  echo "passphrase: from GIE_PAGE_PASS"
else
  die "no shared passphrase: set GIE_PAGE_PASS or write it to ~/.gie-page-passphrase"
fi

uv run --project "$REPO_ROOT" --with cryptography python "$ENCRYPT" \
    --in "$SRC" --out "$OUT" --skip-if-unchanged \
  || die "encryption failed — the site is unchanged"

git -C "$REPO_ROOT" status --short -- "$OUT" || true
echo "Next: commit the ciphertext and open a PR against v1."
