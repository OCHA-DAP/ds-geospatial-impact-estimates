#!/usr/bin/env bash
# List paper artefact CSVs that differ from the frozen-v3 centroid tag, with a per-file row/col summary.
cd "$(dirname "$0")"
TAG=paper-frozen-v3-centroid
for f in $(git status --short -- . | awk '$1=="M"||$1=="??"{print $2}' | grep -E '\.csv$'); do
  rel=$(git ls-files --full-name "$f" 2>/dev/null); rel=${rel:-exploratory/paper/artefacts/$f}
  if git cat-file -e "$TAG:$rel" 2>/dev/null; then echo "### $f (changed)"; else echo "### $f (NEW)"; fi
done
