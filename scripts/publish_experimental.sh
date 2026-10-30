#!/usr/bin/env bash
#
# Encrypt the experimental (Nepal) pages into pages/experimental/.
#
#   ./scripts/publish_experimental.sh            # hub + all three Nepal pages
#   ./scripts/publish_experimental.sh hub        # just the index page
#   ./scripts/publish_experimental.sh precursors # langtang-sar-precursors
#   ./scripts/publish_experimental.sh langtang   # langtang-facet-watch
#   ./scripts/publish_experimental.sh himalaya   # himalaya-facet-watch
#
# Why this exists: the Nepal pages are gated (ADR-0041), so pages/ holds only ciphertext. The
# build scripts in exploratory/0005-nepal-glof-sar-precursor/ write their finished page
# documents to that directory's gitignored data/ as <name>.page.html; this script encrypts
# those into pages/experimental/<name>/content.enc. Re-running a build script does NOT update
# the site until this has run and the result is on v1 — the same rule as publish_pages.sh.
#
# This does not render anything. Rendering the dashboards needs the GEE exports and the
# Sentinel-1 stacks in data/, which only exist on the machine that built them. If an input is
# missing, this fails and names the build script that produces it.
#
# It does not commit or push either. Pushing to v1 is what makes a page public, so that stays
# a decision you make.
#
# Passphrase — the EXPERIMENTAL one, never the shared damage-evaluation passphrase (which
# external reviewers hold): GIE_PAGE_PASS_EXPERIMENTAL, else ~/.gie-page-passphrase-experimental.
# No prompt and no fallback to GIE_PAGE_PASS: falling through to the shared passphrase would
# silently hand the Nepal pages to everyone holding it.

set -euo pipefail

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

TARGET=all
for arg in "$@"; do
  case "$arg" in
    hub|precursors|langtang|himalaya|all) TARGET="$arg" ;;
    -h|--help) sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown argument '$arg' (expected: hub | precursors | langtang | himalaya | all)" ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
NEPAL_DIR="$REPO_ROOT/exploratory/0005-nepal-glof-sar-precursor"
PAGES_DIR="${GIE_PAGES_DIR:-$REPO_ROOT/pages}/experimental"
ENCRYPT="$REPO_ROOT/scripts/encrypt_page.py"

[[ -d $PAGES_DIR ]] || die "pages/experimental/ not found: $PAGES_DIR"
[[ -f $ENCRYPT ]] || die "missing $ENCRYPT"

# Read once, up front, and export under the name encrypt_page.py reads. Fail before touching
# anything if it is absent — see the header for why there is no fallback.
PASS="${GIE_PAGE_PASS_EXPERIMENTAL:-}"
if [[ -z $PASS && -r $HOME/.gie-page-passphrase-experimental ]]; then
  PASS="$(< "$HOME/.gie-page-passphrase-experimental")"
  echo "passphrase: read from ~/.gie-page-passphrase-experimental"
elif [[ -n $PASS ]]; then
  echo "passphrase: from GIE_PAGE_PASS_EXPERIMENTAL"
else
  die "no experimental passphrase.
  Set GIE_PAGE_PASS_EXPERIMENTAL, or write it to ~/.gie-page-passphrase-experimental (chmod 600).
  This is deliberately NOT the shared passphrase in ~/.gie-page-passphrase."
fi
[[ -n $PASS ]] || die "experimental passphrase is empty"
export GIE_PAGE_PASS="$PASS"

CHANGED=()

# encrypt <input html> <output content.enc> <what produces the input>
encrypt() {
  local html=$1 out=$2 producer=$3
  step "Encrypting $(basename "$html")"
  [[ -f $html ]] || die "input not found: $html
  It is produced by: $producer"
  [[ -d $(dirname "$out") ]] || die "output directory missing: $(dirname "$out")"
  # --skip-if-unchanged leaves the file alone when the document is byte-identical to what is
  # already published, so a no-op run does not add megabytes of fresh ciphertext to history.
  uv run --project "$REPO_ROOT" --with cryptography python "$ENCRYPT" \
      --in "$html" --out "$out" --skip-if-unchanged \
    || die "encryption failed for $(basename "$html") — the site is unchanged"
  CHANGED+=("$out")
}

if [[ $TARGET == all || $TARGET == hub ]]; then
  encrypt "$NEPAL_DIR/reports/experimental_hub.html" "$PAGES_DIR/content.enc" \
    "hand-edited source, tracked in git"
fi
if [[ $TARGET == all || $TARGET == precursors ]]; then
  encrypt "$NEPAL_DIR/data/langtang-sar-precursors.page.html" \
    "$PAGES_DIR/langtang-sar-precursors/content.enc" \
    "uv run python $NEPAL_DIR/reports/build_reports.py"
fi
if [[ $TARGET == all || $TARGET == langtang ]]; then
  encrypt "$NEPAL_DIR/data/langtang-facet-watch.page.html" \
    "$PAGES_DIR/langtang-facet-watch/content.enc" \
    "uv run --group etl --with rasterio,matplotlib,geopandas python $NEPAL_DIR/live_build.py"
fi
if [[ $TARGET == all || $TARGET == himalaya ]]; then
  encrypt "$NEPAL_DIR/data/himalaya-facet-watch.page.html" \
    "$PAGES_DIR/himalaya-facet-watch/content.enc" \
    "uv run --group etl --with rasterio,matplotlib,geopandas python $NEPAL_DIR/himalaya_build.py"
fi

step "Done"
git -C "$REPO_ROOT" status --short -- "$PAGES_DIR" || true
echo
echo "Next: review, then commit pages/experimental/ and open a PR against v1."
echo "Merging is what makes the pages live."
