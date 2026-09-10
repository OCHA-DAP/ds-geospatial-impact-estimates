#!/usr/bin/env bash
# ADR-0030 refreeze: re-run the paper artefact chain in dependency order, one log per script, stop on first failure.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p _refreeze_logs
PY="uv run --group etl --with scipy --with scikit-learn --with matplotlib --with h3 python"
run() { local name=$1; shift; echo "== $(date +%H:%M:%S) $name"; $PY "$@" > "_refreeze_logs/$name.log" 2>&1 || { echo "FAILED: $name (see _refreeze_logs/$name.log)"; exit 1; }; }
run rq2q            RQ2-cems-footprint-points/scripts/rq2q_incl_possibly.py
GIE_DUMP_OOF=1 GIE_LABEL_R=10 run rq8_r10  RQ8-learned-fusion/scripts/rq8_learned_fusion.py
GIE_LABEL_R=20 run rq8_r20  RQ8-learned-fusion/scripts/rq8_learned_fusion.py
GIE_LABEL_R=30 run rq8_r30  RQ8-learned-fusion/scripts/rq8_learned_fusion.py
GIE_LABEL_R=10 run rq8b_r10 RQ8-learned-fusion/scripts/rq8b_asdelivered_baseline.py
GIE_LABEL_R=20 run rq8b_r20 RQ8-learned-fusion/scripts/rq8b_asdelivered_baseline.py
run rq8c            RQ8-learned-fusion/scripts/rq8c_basis_sensitivity.py
run rq8d            RQ8-learned-fusion/scripts/rq8d_null_ablation.py
run rq2r            RQ2-cems-footprint-points/scripts/rq2r_precision_bounds.py
run rq9             RQ9-uncertainty/scripts/rq9_block_bootstrap.py
for s in rq2_chatmap_recall rq2_density_null rq2f_vicinity rq2h_osu_v0_v1 rq2j_caraballeda_compare rq2j_hex_performance_maps rq2k_field_union_precision rq2l_cems_grade_recall rq2o_uh_west_strip rq2p_osu_v1_tiers; do
  run $s RQ2-cems-footprint-points/scripts/$s.py
done
for s in rq3b_per_area_moran rq3d_lisa_reliability rq3e_reference_free rq3f_null_ranking rq3g_frac_ranking rq3h_agreement_ranking; do
  run $s RQ3-prioritization-error-structure/scripts/$s.py
done
run rq5_ensemble    RQ5-ensemble/scripts/rq5_ensemble.py
run rq5d            RQ5-ensemble/scripts/rq5d_filtering_null.py
run rq7_consensus   RQ7-mapswipe-validation/scripts/rq7_consensus_fp_adjudication.py
run rq7_round2      RQ7-mapswipe-validation/scripts/rq7_round2_replication.py
run rq7_explainer   RQ7-mapswipe-validation/scripts/rq7_round2_explainer_fig.py
echo "== $(date +%H:%M:%S) ALL DONE"
