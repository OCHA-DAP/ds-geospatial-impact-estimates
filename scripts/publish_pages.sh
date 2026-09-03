#!/usr/bin/env bash
#
# Publish the paper artefacts to the Pages site: render, encrypt, commit.
#
#   ./scripts/publish_pages.sh            # both: render, encrypt, commit
#   ./scripts/publish_pages.sh deck       # just the results deck
#   ./scripts/publish_pages.sh paper      # just the manuscript
#   ./scripts/publish_pages.sh brief      # just the technical brief
#   ./scripts/publish_pages.sh briefing   # just the A&A Cell 5-slide briefing
#   ./scripts/publish_pages.sh --ship     # ...and push + open a PR against v1
#   ./scripts/publish_pages.sh deck --no-commit
#
# --ship stops at the PR. Merging is what makes an artefact public, so it stays a decision
# someone makes on purpose rather than a side effect of running this.
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
# Paths, overridable when the paper sources and pages/ live in different worktrees. Set them once
# in scripts/publish_pages.env (gitignored, sourced automatically) instead of typing them:
#   GIE_PAPER_DIR   default <repo>/exploratory/paper
#   GIE_PAGES_DIR   default <repo>/pages
# Passphrase: GIE_PAGE_PASS, else ~/.gie-page-passphrase, else encrypt_page.py prompts.

set -euo pipefail

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

TARGET=all
COMMIT=yes
SHIP=no
for arg in "$@"; do
  case "$arg" in
    deck|paper|briefing|brief|all) TARGET="$arg" ;;
    --no-commit)    COMMIT=no ;;
    --ship)         SHIP=yes ;;
    -h|--help)      sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)              die "unknown argument '$arg' (expected: deck | paper | briefing | brief | all | --ship | --no-commit)" ;;
  esac
done
[[ $SHIP == yes && $COMMIT == no ]] && die "--ship and --no-commit contradict each other"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"

# Local, gitignored overrides so the paths are configured once rather than typed every time.
# Needed while the paper branch is unmerged and the sources live in a different worktree.
if [[ -r $SCRIPT_DIR/publish_pages.env ]]; then
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/publish_pages.env"
  echo "config: scripts/publish_pages.env"
fi

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

PAGES_REPO="$(git -C "$PAGES_DIR" rev-parse --show-toplevel)"

# --ship publishes for real, so set up the branch BEFORE rendering: switching branches later,
# with a freshly encrypted content.enc in the way, would conflict against the published version.
if [[ $SHIP == yes ]]; then
  git -C "$PAGES_REPO" diff --quiet && git -C "$PAGES_REPO" diff --cached --quiet \
    || die "--ship needs a clean tree in $PAGES_REPO; commit or stash first"
  step "Preparing a branch off v1"
  git -C "$PAGES_REPO" fetch -q origin
  SHIP_BRANCH="republish-$(date -u +%Y%m%d-%H%M%S)"
  git -C "$PAGES_REPO" checkout -q -b "$SHIP_BRANCH" origin/v1
  echo "  $SHIP_BRANCH (from origin/v1)"
fi

# Quarto needs a Python carrying the notebook stack; the project venv does not have it, and the
# repo's .python-version pins a pyenv build that is not installed, so a bare `quarto render`
# fails. This is the incantation from exploratory/paper/README.md.
render() {
  local qmd=$1 fmt=$2
  step "Rendering $qmd --to $fmt"
  ( cd "$PAPER_DIR" && uv run --group etl \
      --with nbformat --with nbclient --with ipykernel \
      --with matplotlib --with numpy --with shapely --with great-tables bash -c \
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
  render satellite_damage_evaluation_deck_v2.qmd revealjs
  encrypt satellite_damage_evaluation_deck_v2.html "$PAGES_DIR/slides/damage-evaluation/content.enc"
fi

if [[ $TARGET == all || $TARGET == briefing ]]; then
  render aa_cell_briefing_deck.qmd revealjs
  encrypt aa_cell_briefing_deck.html "$PAGES_DIR/slides/aa-cell-briefing/content.enc"
fi

if [[ $TARGET == all || $TARGET == paper ]]; then
  render manuscript_v3.qmd html
  encrypt manuscript_v3.html "$PAGES_DIR/manuscript/content.enc"
fi

if [[ $TARGET == all || $TARGET == brief ]]; then
  render manuscript_brief.qmd html
  encrypt manuscript_brief.html "$PAGES_DIR/brief/content.enc"
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

# status --porcelain also sees UNTRACKED files (a first-time target's content.enc),
# which the diff pair used here previously did not.
if [[ -z "$(git -C "$PAGES_REPO" status --porcelain -- "$PAGES_DIR")" ]]; then
  step "Nothing to commit"
  echo "  The re-rendered artefacts are byte-identical to what is already published."
  if [[ $SHIP == yes ]]; then
    git -C "$PAGES_REPO" checkout -q -; git -C "$PAGES_REPO" branch -q -D "$SHIP_BRANCH"
    echo "  Dropped the empty branch; the live site is already current."
  fi
  exit 0
fi

step "Committing"
git -C "$PAGES_REPO" add -- "$PAGES_DIR"
git -C "$PAGES_REPO" commit -q -m "pages: republish $( [[ $TARGET == all ]] && echo 'deck, briefing, manuscript and brief' || echo "$TARGET" )

Re-rendered from exploratory/paper and re-encrypted. Content only; no code change."
git -C "$PAGES_REPO" --no-pager log --oneline -1

BRANCH="$(git -C "$PAGES_REPO" rev-parse --abbrev-ref HEAD)"

if [[ $SHIP == no ]]; then
  cat <<EOF

Committed on '$BRANCH'. Nothing is public yet — the deploy fires when pages/ lands on v1:

  git -C $PAGES_REPO push origin $BRANCH
  gh pr create --base v1 --head $BRANCH --fill

Or re-run with --ship to do both automatically.

Then check: https://ocha-dap.github.io/ds-geospatial-impact-estimates/
EOF
  exit 0
fi

# --ship pushes and opens the PR. It deliberately stops short of merging: merging to v1 is what
# makes the artefact public, and that stays a decision someone makes on purpose, not a side
# effect of a publish script.
step "Pushing and opening a PR"
git -C "$PAGES_REPO" push -q origin "$BRANCH" || die "push failed — nothing is public"
PR_URL="$(cd "$PAGES_REPO" && gh pr create --base v1 --head "$BRANCH" \
  --title "pages: republish $( [[ $TARGET == all ]] && echo 'deck, briefing, manuscript and brief' || echo "$TARGET" )" \
  --body "Re-rendered from \`exploratory/paper\` and re-encrypted. Content only; no code change.

Opened by \`scripts/publish_pages.sh --ship\`.")" \
  || die "could not open a PR — the branch is pushed, so finish it by hand"

cat <<EOF

  $PR_URL

Review it, then merge to publish — that fires the deploy:

  gh pr merge $PR_URL --merge

Then check: https://ocha-dap.github.io/ds-geospatial-impact-estimates/
EOF
