#!/usr/bin/env bash
#
# Publish the paper artefacts to the Pages site: render, encrypt, commit.
#
#   ./scripts/publish_pages.sh            # both
#   ./scripts/publish_pages.sh deck       # just the results deck
#   ./scripts/publish_pages.sh paper      # just the manuscript
#   ./scripts/publish_pages.sh deck --no-commit
#
# Why this script exists: the site serves `content.enc`, an encrypted snapshot of the *rendered*
# HTML. Pushing .qmd changes does not update the site. Rendering cannot run in CI — the figure
# PNGs are gitignored and rebuilding them needs the Azure data lake — so publishing is a local,
# deliberate act. Doing it by hand is a multi-line `uv run` incantation per artefact, which is
# easy to get wrong or half-finish, leaving the site quietly showing an older version.
#
# It never pushes. Pushing to trunk is what triggers the public deploy, and that stays a
# decision you make, not a side effect of running this.
#
# Paths, overridable when the paper sources and pages/ live in different worktrees:
#   GIE_PAPER_DIR   default <repo>/exploratory/paper
#   GIE_PAGES_DIR   default <repo>/pages
# Passphrase: GIE_PAGE_PASS, else ~/.gie-page-passphrase, else encrypt_page.py prompts.

set -euo pipefail

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

TARGET=all
COMMIT=yes
for arg in "$@"; do
  case "$arg" in
    deck|paper|all) TARGET="$arg" ;;
    --no-commit)    COMMIT=no ;;
    -h|--help)      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)              die "unknown argument '$arg' (expected: deck | paper | all | --no-commit)" ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
PAPER_DIR="${GIE_PAPER_DIR:-$REPO_ROOT/exploratory/paper}"
PAGES_DIR="${GIE_PAGES_DIR:-$REPO_ROOT/pages}"
ENCRYPT="$REPO_ROOT/scripts/encrypt_page.py"

[[ -d $PAPER_DIR ]] || die "paper sources not found: $PAPER_DIR
  The .qmd sources live on the analysis branch. If that is a different worktree, point at it:
    GIE_PAPER_DIR=/path/to/worktree/exploratory/paper $0 $TARGET"
[[ -d $PAGES_DIR ]] || die "pages/ not found: $PAGES_DIR
  pages/ lives on v1. If you are in a worktree that predates it, point at the one that has it:
    GIE_PAGES_DIR=/path/to/worktree/pages $0 $TARGET"
[[ -f $ENCRYPT ]] || die "missing $ENCRYPT"

# Read the passphrase once, here, so a missing one fails before we spend minutes rendering.
if [[ -z ${GIE_PAGE_PASS:-} ]] && [[ -r $HOME/.gie-page-passphrase ]]; then
  GIE_PAGE_PASS="$(< "$HOME/.gie-page-passphrase")"
  export GIE_PAGE_PASS
  echo "passphrase: read from ~/.gie-page-passphrase"
elif [[ -n ${GIE_PAGE_PASS:-} ]]; then
  echo "passphrase: from GIE_PAGE_PASS"
else
  echo "passphrase: none found — encrypt_page.py will prompt"
fi

# Quarto needs a Python carrying the notebook stack; the project venv does not have it, and the
# repo's .python-version pins a pyenv build that is not installed, so a bare `quarto render`
# fails. This is the incantation from exploratory/paper/README.md.
render() {
  local qmd=$1 fmt=$2
  step "Rendering $qmd --to $fmt"
  ( cd "$PAPER_DIR" && uv run --group etl \
      --with nbformat --with nbclient --with ipykernel \
      --with matplotlib --with numpy --with shapely bash -c \
      "QUARTO_PYTHON=\"\$(python -c 'import sys; print(sys.executable)')\" \
       quarto render $qmd --to $fmt" ) \
    || die "render failed for $qmd — the site is unchanged"
}

encrypt() {
  local html=$1 out=$2
  step "Encrypting $(basename "$html")"
  mkdir -p "$(dirname "$out")"
  # --skip-if-unchanged leaves the file alone when the document is byte-identical to what is
  # already published, so a no-op run does not add megabytes of fresh ciphertext to history.
  uv run --project "$REPO_ROOT" --with cryptography python "$ENCRYPT" \
      --in "$PAPER_DIR/$html" --out "$out" --skip-if-unchanged \
    || die "encryption failed for $html — the site is unchanged"
  CHANGED+=("$out")
}

CHANGED=()

if [[ $TARGET == all || $TARGET == deck ]]; then
  render satellite_damage_evaluation_v2.qmd revealjs
  encrypt satellite_damage_evaluation_v2.html "$PAGES_DIR/slides/damage-evaluation/content.enc"
fi

if [[ $TARGET == all || $TARGET == paper ]]; then
  render manuscript_v2.qmd html
  encrypt manuscript_v2.html "$PAGES_DIR/manuscript/content.enc"
fi

step "Result"
for f in "${CHANGED[@]}"; do
  printf '  %s  (%s)\n' "${f#"$REPO_ROOT"/}" "$(du -h "$f" | cut -f1)"
done

if [[ $COMMIT == no ]]; then
  echo
  echo "Not committing (--no-commit). The site updates only once pages/ reaches v1."
  exit 0
fi

PAGES_REPO="$(git -C "$PAGES_DIR" rev-parse --show-toplevel)"
if git -C "$PAGES_REPO" diff --quiet -- "$PAGES_DIR" && \
   git -C "$PAGES_REPO" diff --cached --quiet -- "$PAGES_DIR"; then
  step "Nothing to commit"
  echo "  The re-rendered artefacts are byte-identical to what is already published."
  exit 0
fi

step "Committing"
git -C "$PAGES_REPO" add -- "$PAGES_DIR"
git -C "$PAGES_REPO" commit -q -m "pages: republish $( [[ $TARGET == all ]] && echo 'deck and manuscript' || echo "$TARGET" )

Re-rendered from exploratory/paper and re-encrypted. Content only; no code change."
git -C "$PAGES_REPO" --no-pager log --oneline -1

BRANCH="$(git -C "$PAGES_REPO" rev-parse --abbrev-ref HEAD)"
cat <<EOF

Committed on '$BRANCH'. Nothing is public yet — the deploy fires when pages/ lands on v1:

  git -C $PAGES_REPO push origin $BRANCH
  gh pr create --base v1 --head $BRANCH --fill && gh pr merge --merge

Then check: https://ocha-dap.github.io/ds-geospatial-impact-estimates/
EOF
