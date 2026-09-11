#!/usr/bin/env bash
# ADR-0030 refreeze, part 3: uncited-but-frozen artefacts so nothing in the tree stays on the old frame.
set -euo pipefail
cd "$(dirname "$0")"
PY="uv run --group etl --with scipy --with scikit-learn --with matplotlib --with h3 --with statsmodels --with rasterio python"
run() { local name=$1; shift; echo "== $(date +%H:%M:%S) $name"; $PY "$@" > "_refreeze_logs/$name.log" 2>&1 || { echo "FAILED: $name (see _refreeze_logs/$name.log)"; exit 1; }; }
run rq0_cloud   RQ0-matching-basis/scripts/rq0_cloud_unknown_robustness.py
GIE_LABEL_R=30 run rq8b_r30 RQ8-learned-fusion/scripts/rq8b_asdelivered_baseline.py
GIE_CV_BUFFER_M=300 run rq8_buf300 RQ8-learned-fusion/scripts/rq8_learned_fusion.py
GIE_CV_BUFFER_M=500 run rq8_buf500 RQ8-learned-fusion/scripts/rq8_learned_fusion.py
echo "== $(date +%H:%M:%S) TAIL DONE"
