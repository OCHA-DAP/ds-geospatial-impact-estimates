#!/bin/bash
# Re-pin all CEMS-dependent analyses against the latest-only cems_points() (freeze batch).
cd /Users/zackarno/Documents/CHD/repos/ds-geospatial-impact-estimates
A=exploratory/paper/artefacts
LOG=$A/_freeze_batch.log
: > $LOG
run() {
  echo "=== $1 ($(date +%H:%M:%S))" >> $LOG
  uv run --group etl --with scipy --with matplotlib --with statsmodels python "$1" >> $LOG 2>&1
  echo "--- exit $? " >> $LOG
}
run $A/RQ2-cems-footprint-points/scripts/rq2_points.py
run $A/RQ2-cems-footprint-points/scripts/rq2_density_null.py
run $A/RQ2-cems-footprint-points/scripts/rq2_ms_confidence.py
run $A/RQ2-cems-footprint-points/scripts/rq2_chatmap_recall.py
run $A/RQ3-prioritization-error-structure/scripts/rq3_prioritization.py
run $A/RQ3-prioritization-error-structure/scripts/rq3_error_structure.py
run $A/RQ3-prioritization-error-structure/scripts/rq3b_per_area_moran.py
run $A/RQ4-unep-enclosed-admin/scripts/rq4_enclosed_admin.py
run $A/RQ5-ensemble/scripts/rq5_ensemble.py
run $A/RQ5-ensemble/scripts/rq5b_six_member.py
run $A/RQ6-diy-sar/scripts/rq6_score.py
run $A/RQ7-mapswipe-validation/scripts/rq7_west_cluster.py
run $A/RQ7-mapswipe-validation/scripts/rq7_consensus_fp_adjudication.py
echo "BATCH DONE $(date +%H:%M:%S)" >> $LOG
