#!/usr/bin/env bash
# ADR-0031: re-run everything that computes or consumes the crowd adjustment.
set -euo pipefail
cd "$(dirname "$0")"
PY="uv run --group etl --with scipy --with scikit-learn --with matplotlib --with h3 --with statsmodels python"
run() { local name=$1; shift; echo "== $(date +%H:%M:%S) $name"; $PY "$@" > "_refreeze_logs/$name.log" 2>&1 || { echo "FAILED: $name (see _refreeze_logs/$name.log)"; exit 1; }; }
run rq5b_r10 RQ5-ensemble/scripts/rq5b_six_member.py
GIE_LABEL_R=20 run rq5b_r20 RQ5-ensemble/scripts/rq5b_six_member.py
GIE_LABEL_R=30 run rq5b_r30 RQ5-ensemble/scripts/rq5b_six_member.py
run rq2i     RQ2-cems-footprint-points/scripts/rq2i_per_aoi_scorecard.py
run rq2r     RQ2-cems-footprint-points/scripts/rq2r_precision_bounds.py
run rq9      RQ9-uncertainty/scripts/rq9_block_bootstrap.py
run rq7_round2 RQ7-mapswipe-validation/scripts/rq7_round2_replication.py
run fig_rq5b RQ5-ensemble/scripts/rq5b_frontier_fig.py
echo "== $(date +%H:%M:%S) CROWD DONE"
