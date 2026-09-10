#!/usr/bin/env bash
# ADR-0030 refreeze, part 2: redraw the brief's figures that are drawn from CSVs by separate fig scripts.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p _refreeze_logs
PY="uv run --group etl --with scipy --with scikit-learn --with matplotlib --with h3 --with statsmodels python"
run() { local name=$1; shift; echo "== $(date +%H:%M:%S) $name"; $PY "$@" > "_refreeze_logs/$name.log" 2>&1 || { echo "FAILED: $name (see _refreeze_logs/$name.log)"; exit 1; }; }
run fig_rq2e   RQ2-cems-footprint-points/scripts/rq2e_grade_slope_fig.py
run fig_rq2r   RQ2-cems-footprint-points/scripts/rq2r_bounds_fig.py
run fig_rq5b   RQ5-ensemble/scripts/rq5b_frontier_fig.py
run fig_rq8c   RQ8-learned-fusion/scripts/rq8c_basis_fig.py
run fig_rq8    RQ8-learned-fusion/scripts/rq8_best_f1_fig.py --summary
run fig_rq3f   RQ3-prioritization-error-structure/scripts/rq3f_null_ranking_both_fig.py --summary
run fig_rq3h   RQ3-prioritization-error-structure/scripts/rq3h_agreement_ranking_fig.py --summary
echo "== $(date +%H:%M:%S) FIGS DONE"
