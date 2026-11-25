# results.csv: 0c9cc12 → working tree

559 changed, 227 added, 12 removed (of 3160 rows)

| region | lens | r | predictor | metric | base | now | Δ | source |
|---|---|---|---|---|---|---|---|---|
| Caraballeda | density | nan | MS | n_flag | 7944 | 7950 | +6.000 | RQ2-cems-footprint-points/rq2_density_null.csv |
| Caraballeda | density | nan | UH | P | 0.126 | 0.124 | -0.002 | RQ2-cems-footprint-points/rq2_density_null.csv |
| Caraballeda | density | nan | UH | flag_pct | 9.4 | 9.5 | +0.100 | RQ2-cems-footprint-points/rq2_density_null.csv |
| Caraballeda | density | nan | UH | lift | 3.5 | 3.4 | -0.100 | RQ2-cems-footprint-points/rq2_density_null.csv |
| Caraballeda | density | nan | UH | n_flag | 5366 | 5447 | +81.000 | RQ2-cems-footprint-points/rq2_density_null.csv |
| Caracas | density | nan | UH | flag_pct | 17.7 | 18 | +0.300 | RQ2-cems-footprint-points/rq2_density_null.csv |
| Caracas | density | nan | UH | n_flag | 18176 | 18452 | +276.000 | RQ2-cems-footprint-points/rq2_density_null.csv |
| Santa Cruz | density | nan | UH | n_flag | 32145 | 32144 | -1.000 | RQ2-cems-footprint-points/rq2_density_null.csv |
| ALL | moran | 8.0 | MS | moran_I | 0.54 | 0.539 | -0.001 | RQ3-prioritization-error-structure/rq3b_per_area_moran.csv |
| ALL | moran | 8.0 | UH | flag_pct | 19.3 | 19.4 | +0.100 | RQ3-prioritization-error-structure/rq3b_per_area_moran.csv |
| ALL | moran | 8.0 | UH | moran_I | 0.401 | 0.402 | +0.001 | RQ3-prioritization-error-structure/rq3b_per_area_moran.csv |
| Caraballeda | moran | 8.0 | MS | moran_I | 0.54 | 0.539 | -0.001 | RQ3-prioritization-error-structure/rq3b_per_area_moran.csv |
| Caraballeda | moran | 8.0 | UH | flag_pct | 9.4 | 9.5 | +0.100 | RQ3-prioritization-error-structure/rq3b_per_area_moran.csv |
| Caracas | moran | 8.0 | UH | flag_pct | 17.7 | 18 | +0.300 | RQ3-prioritization-error-structure/rq3b_per_area_moran.csv |
| Caracas | moran | 8.0 | UH | moran_I | 0.374 | 0.379 | +0.005 | RQ3-prioritization-error-structure/rq3b_per_area_moran.csv |
| asd | lisa | 8.0 | UNEP | HH | 14 | 13 | -1.000 | RQ3-prioritization-error-structure/rq3d_lisa_summary.csv |
| asd | lisa | 8.0 | UNEP | LH | 6 | 5 | -1.000 | RQ3-prioritization-error-structure/rq3d_lisa_summary.csv |
| asd | lisa | 8.0 | UNEP | ns | 112 | 114 | +2.000 | RQ3-prioritization-error-structure/rq3d_lisa_summary.csv |
| asd | cells-fraction | 7.0 | UH | cells_count | 106 | 107 | +1.000 | RQ3-prioritization-error-structure/rq3g_frac_vs_count.csv |
| asd | cells-fraction | 7.0 | UH | rho_count | -0.085 | -0.073 | +0.012 | RQ3-prioritization-error-structure/rq3g_frac_vs_count.csv |
| asd | cells-fraction | 7.0 | UH | rho_frac | -0.211 | -0.21 | +0.001 | RQ3-prioritization-error-structure/rq3g_frac_vs_count.csv |
| asd | cells-fraction | 7.0 | UH | rho_null_count | 0.698 | 0.696 | -0.002 | RQ3-prioritization-error-structure/rq3g_frac_vs_count.csv |
| asd | cells-fraction | 7.0 | UNEP | rho_count | 0.219 | 0.222 | +0.003 | RQ3-prioritization-error-structure/rq3g_frac_vs_count.csv |
| asd | cells-fraction | 7.0 | UNEP | rho_frac | 0.139 | 0.143 | +0.004 | RQ3-prioritization-error-structure/rq3g_frac_vs_count.csv |
| asd | cells-fraction | 8.0 | Microsoft | rho_frac | 0.362 | 0.36 | -0.002 | RQ3-prioritization-error-structure/rq3g_frac_vs_count.csv |
| asd | cells-fraction | 8.0 | UH | cells_count | 453 | 454 | +1.000 | RQ3-prioritization-error-structure/rq3g_frac_vs_count.csv |
| asd | cells-fraction | 8.0 | UH | rho_frac | -0.21 | -0.212 | -0.002 | RQ3-prioritization-error-structure/rq3g_frac_vs_count.csv |
| asd | cells-fraction | 8.0 | UNEP | cells_count | 601 | 602 | +1.000 | RQ3-prioritization-error-structure/rq3g_frac_vs_count.csv |
| asd | cells-fraction | 8.0 | UNEP | cells_frac | 582 | 583 | +1.000 | RQ3-prioritization-error-structure/rq3g_frac_vs_count.csv |
| asd | cells-fraction | 8.0 | UNEP | rho_count | 0.068 | 0.071 | +0.003 | RQ3-prioritization-error-structure/rq3g_frac_vs_count.csv |
| asd | cells-fraction | 8.0 | UNEP | rho_frac | 0.08 | 0.084 | +0.004 | RQ3-prioritization-error-structure/rq3g_frac_vs_count.csv |
| asd | cells-fraction | 8.0 | UNEP | rho_null_frac | 0.469 | 0.467 | -0.002 | RQ3-prioritization-error-structure/rq3g_frac_vs_count.csv |
| asd | crowd-round2 | 10.0 | LIST | P_crowd_r2swap | 0.078 | 0.076 | -0.002 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| asd | crowd-round2 | 10.0 | LIST | delta | 0.002 | 0 | -0.002 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| asd | crowd-round2 | 10.0 | MS | P_crowd_r2swap | 0.257 | 0.256 | -0.001 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| asd | crowd-round2 | 10.0 | MS | conf_r1 | 0.127564 | 0.127465 | -0.000 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| asd | crowd-round2 | 10.0 | MS | conf_r2 | 0.111094 | 0.111318 | +0.000 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| asd | crowd-round2 | 10.0 | MS | delta | -0.011 | -0.012 | -0.001 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| asd | crowd-round2 | 10.0 | MS | strip_unmatched | 6436 | 6441 | +5.000 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| asd | crowd-round2 | 10.0 | OSU | P_crowd_r2swap | 0.105 | 0.109 | +0.004 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| asd | crowd-round2 | 10.0 | OSU | delta | -0.01 | -0.006 | +0.004 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| asd | crowd-round2 | 10.0 | UH | P_crowd_r2swap | 0.022 | 0.019 | -0.003 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| asd | crowd-round2 | 10.0 | UH | delta | 0.002 | -0.001 | -0.003 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| asd | crowd-round2 | 10.0 | UH | strip_share | 0.428 | 0.425 | -0.003 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| asd | crowd-round2 | 10.0 | UNEP | P_crowd_r2swap | 0.075 | 0.072 | -0.003 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| asd | crowd-round2 | 10.0 | UNEP | conf_r1 | 0.151676 | 0.151466 | -0.000 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| asd | crowd-round2 | 10.0 | UNEP | conf_r2 | 0.110058 | 0.110829 | +0.001 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| asd | crowd-round2 | 10.0 | UNEP | delta | -0.006 | -0.009 | -0.003 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| asd | crowd-round2 | 10.0 | UNEP | strip_share | 0.966 | 0.964 | -0.002 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| asd | crowd-round2 | 10.0 | UNEP | strip_unmatched | 4325 | 4331 | +6.000 | RQ7-mapswipe-validation/rq7_round2_padj_sensitivity.csv |
| strip | crowd-round2 | nan | MS | ms_cems_matched | 544 | 545 | +1.000 | RQ7-mapswipe-validation/rq7_round2_replication.csv |
| strip | crowd-round2 | nan | MS | ms_flags_in_cells | 6980 | 6986 | +6.000 | RQ7-mapswipe-validation/rq7_round2_replication.csv |
| strip | crowd-round2 | nan | MS | ms_unmatched | 6436 | 6441 | +5.000 | RQ7-mapswipe-validation/rq7_round2_replication.csv |
| strip | crowd-round2 | nan | MS | ms_unmatched_conf_share_r1 | 0.127564 | 0.127465 | -0.000 | RQ7-mapswipe-validation/rq7_round2_replication.csv |
| strip | crowd-round2 | nan | MS | ms_unmatched_conf_share_r2 | 0.111094 | 0.111318 | +0.000 | RQ7-mapswipe-validation/rq7_round2_replication.csv |
| core | labels | 10.0 | MS | R | 0.464 | 0.465 | +0.001 | RQ8-learned-fusion/rq8_best_f1_r10.csv |
| core | labels | 10.0 | MS | n_flags | 7872 | 7878 | +6.000 | RQ8-learned-fusion/rq8_best_f1_r10.csv |
| core | labels | 10.0 | UH | F1 | 0.182 | 0.18 | -0.002 | RQ8-learned-fusion/rq8_best_f1_r10.csv |
| core | labels | 10.0 | UH | P | 0.126 | 0.124 | -0.002 | RQ8-learned-fusion/rq8_best_f1_r10.csv |
| core | labels | 10.0 | UH | n_flags | 5362 | 5443 | +81.000 | RQ8-learned-fusion/rq8_best_f1_r10.csv |
| core | labels | 10.0 | UNEP | F1 | 0.172 | 0.171 | -0.001 | RQ8-learned-fusion/rq8_best_f1_r10.csv |
| core | labels | 10.0 | UNEP | R | 0.319 | 0.317 | -0.002 | RQ8-learned-fusion/rq8_best_f1_r10.csv |
| core | labels | 10.0 | UNEP | n_flags | 5604 | 5605 | +1.000 | RQ8-learned-fusion/rq8_best_f1_r10.csv |
| core | labels | 10.0 | flat k-of-6 voting | F1 | 0.324 | 0.323 | -0.001 | RQ8-learned-fusion/rq8_best_f1_r10.csv |
| core | labels | 10.0 | flat k-of-6 voting | P | 0.269 | 0.268 | -0.001 | RQ8-learned-fusion/rq8_best_f1_r10.csv |
| core | labels | 10.0 | flat k-of-6 voting | n_flags | 3114 | 3123 | +9.000 | RQ8-learned-fusion/rq8_best_f1_r10.csv |
| core | labels | 10.0 | weighted fusion | F1 | 0.374 | 0.371 | -0.003 | RQ8-learned-fusion/rq8_best_f1_r10.csv |
| core | labels | 10.0 | weighted fusion | P | 0.358 | 0.37 | +0.012 | RQ8-learned-fusion/rq8_best_f1_r10.csv |
| core | labels | 10.0 | weighted fusion | R | 0.39 | 0.372 | -0.018 | RQ8-learned-fusion/rq8_best_f1_r10.csv |
| core | labels | 10.0 | weighted fusion | n_flags | 2246 | 2075 | -171.000 | RQ8-learned-fusion/rq8_best_f1_r10.csv |
| core | labels | 10.0 | weighted fusion | threshold | 0.873 | 0.8806 | +0.008 | RQ8-learned-fusion/rq8_best_f1_r10.csv |
| core | labels | 20.0 | MS | n_flags | 7872 | 7878 | +6.000 | RQ8-learned-fusion/rq8_best_f1_r20.csv |
| core | labels | 20.0 | UH | F1 | 0.215 | 0.214 | -0.001 | RQ8-learned-fusion/rq8_best_f1_r20.csv |
| core | labels | 20.0 | UH | P | 0.182 | 0.18 | -0.002 | RQ8-learned-fusion/rq8_best_f1_r20.csv |
| core | labels | 20.0 | UH | R | 0.262 | 0.263 | +0.001 | RQ8-learned-fusion/rq8_best_f1_r20.csv |
| core | labels | 20.0 | UH | n_flags | 5362 | 5443 | +81.000 | RQ8-learned-fusion/rq8_best_f1_r20.csv |
| core | labels | 20.0 | UNEP | P | 0.17 | 0.171 | +0.001 | RQ8-learned-fusion/rq8_best_f1_r20.csv |
| core | labels | 20.0 | UNEP | R | 0.256 | 0.257 | +0.001 | RQ8-learned-fusion/rq8_best_f1_r20.csv |
| core | labels | 20.0 | UNEP | n_flags | 5604 | 5605 | +1.000 | RQ8-learned-fusion/rq8_best_f1_r20.csv |
| core | labels | 20.0 | flat k-of-6 voting | F1 | 0.35 | 0.351 | +0.001 | RQ8-learned-fusion/rq8_best_f1_r20.csv |
| core | labels | 20.0 | flat k-of-6 voting | R | 0.321 | 0.322 | +0.001 | RQ8-learned-fusion/rq8_best_f1_r20.csv |
| core | labels | 20.0 | flat k-of-6 voting | n_flags | 3114 | 3123 | +9.000 | RQ8-learned-fusion/rq8_best_f1_r20.csv |
| core | labels | 20.0 | weighted fusion | P | 0.41 | 0.411 | +0.001 | RQ8-learned-fusion/rq8_best_f1_r20.csv |
| core | labels | 20.0 | weighted fusion | R | 0.413 | 0.411 | -0.002 | RQ8-learned-fusion/rq8_best_f1_r20.csv |
| core | labels | 20.0 | weighted fusion | n_flags | 3757 | 3726 | -31.000 | RQ8-learned-fusion/rq8_best_f1_r20.csv |
| core | labels | 20.0 | weighted fusion | threshold | 0.819 | 0.8202 | +0.001 | RQ8-learned-fusion/rq8_best_f1_r20.csv |
| core | labels | 30.0 | MS | n_flags | 7872 | 7878 | +6.000 | RQ8-learned-fusion/rq8_best_f1_r30.csv |
| core | labels | 30.0 | UH | F1 | 0.223 | 0.222 | -0.001 | RQ8-learned-fusion/rq8_best_f1_r30.csv |
| core | labels | 30.0 | UH | P | 0.225 | 0.222 | -0.003 | RQ8-learned-fusion/rq8_best_f1_r30.csv |
| core | labels | 30.0 | UH | R | 0.22 | 0.221 | +0.001 | RQ8-learned-fusion/rq8_best_f1_r30.csv |
| core | labels | 30.0 | UH | n_flags | 5362 | 5443 | +81.000 | RQ8-learned-fusion/rq8_best_f1_r30.csv |
| core | labels | 30.0 | UNEP | n_flags | 5604 | 5605 | +1.000 | RQ8-learned-fusion/rq8_best_f1_r30.csv |
| core | labels | 30.0 | flat k-of-6 voting | R | 0.536 | 0.537 | +0.001 | RQ8-learned-fusion/rq8_best_f1_r30.csv |
| core | labels | 30.0 | flat k-of-6 voting | n_flags | 9116 | 9140 | +24.000 | RQ8-learned-fusion/rq8_best_f1_r30.csv |
| core | labels | 30.0 | weighted fusion | P | 0.425 | 0.427 | +0.002 | RQ8-learned-fusion/rq8_best_f1_r30.csv |
| core | labels | 30.0 | weighted fusion | R | 0.486 | 0.482 | -0.004 | RQ8-learned-fusion/rq8_best_f1_r30.csv |
| core | labels | 30.0 | weighted fusion | n_flags | 6259 | 6182 | -77.000 | RQ8-learned-fusion/rq8_best_f1_r30.csv |
| core | labels | 30.0 | weighted fusion | threshold | 0.7588 | 0.7611 | +0.002 | RQ8-learned-fusion/rq8_best_f1_r30.csv |
| asd | labels | 10.0 | MS | R | 0.464 | 0.465 | +0.001 | RQ8-learned-fusion/rq8b_asdelivered_baseline_r10.csv |
| asd | labels | 10.0 | MS | n_flags | 7944 | 7950 | +6.000 | RQ8-learned-fusion/rq8b_asdelivered_baseline_r10.csv |
| asd | labels | 10.0 | UH | R | 0.326 | 0.327 | +0.001 | RQ8-learned-fusion/rq8b_asdelivered_baseline_r10.csv |
| asd | labels | 10.0 | UH | n_flags | 55952 | 56308 | +356.000 | RQ8-learned-fusion/rq8b_asdelivered_baseline_r10.csv |
| asd | labels | 10.0 | UNEP | P_dayzero | 0.065 | 0.064 | -0.001 | RQ8-learned-fusion/rq8b_asdelivered_baseline_r10.csv |
| asd | labels | 10.0 | UNEP | R | 0.312 | 0.31 | -0.002 | RQ8-learned-fusion/rq8b_asdelivered_baseline_r10.csv |
| asd | labels | 10.0 | UNEP | n_flags | 17879 | 17937 | +58.000 | RQ8-learned-fusion/rq8b_asdelivered_baseline_r10.csv |
| asd | labels | 20.0 | MS | n_flags | 7944 | 7950 | +6.000 | RQ8-learned-fusion/rq8b_asdelivered_baseline_r20.csv |
| asd | labels | 20.0 | UH | R | 0.261 | 0.262 | +0.001 | RQ8-learned-fusion/rq8b_asdelivered_baseline_r20.csv |
| asd | labels | 20.0 | UH | R_dayzero | 0.936 | 0.937 | +0.001 | RQ8-learned-fusion/rq8b_asdelivered_baseline_r20.csv |
| asd | labels | 20.0 | UH | n_flags | 55952 | 56308 | +356.000 | RQ8-learned-fusion/rq8b_asdelivered_baseline_r20.csv |
| asd | labels | 20.0 | UNEP | R | 0.25 | 0.251 | +0.001 | RQ8-learned-fusion/rq8b_asdelivered_baseline_r20.csv |
| asd | labels | 20.0 | UNEP | R_dayzero | 0.54 | 0.541 | +0.001 | RQ8-learned-fusion/rq8b_asdelivered_baseline_r20.csv |
| asd | labels | 20.0 | UNEP | n_flags | 17879 | 17937 | +58.000 | RQ8-learned-fusion/rq8b_asdelivered_baseline_r20.csv |
| asd | ci | 10.0 | UH | R | 0.45 | 0.451 | +0.001 | RQ9-uncertainty/rq9_ci_asdelivered_r10.csv |
| asd | ci | 10.0 | UH | R_hi | 0.564 | 0.566 | +0.002 | RQ9-uncertainty/rq9_ci_asdelivered_r10.csv |
| asd | ci | 10.0 | UH | R_lo | 0.326 | 0.327 | +0.001 | RQ9-uncertainty/rq9_ci_asdelivered_r10.csv |
| asd | ci | 10.0 | UNEP | P_hi | 0.068 | 0.067 | -0.001 | RQ9-uncertainty/rq9_ci_asdelivered_r10.csv |
| asd | ci | 10.0 | UNEP | R | 0.425 | 0.421 | -0.004 | RQ9-uncertainty/rq9_ci_asdelivered_r10.csv |
| asd | ci | 10.0 | UNEP | R_hi | 0.47 | 0.468 | -0.002 | RQ9-uncertainty/rq9_ci_asdelivered_r10.csv |
| asd | ci | 10.0 | UNEP | R_lo | 0.333 | 0.329 | -0.004 | RQ9-uncertainty/rq9_ci_asdelivered_r10.csv |
| core | ci | 10.0 | 3-of-6 | F1_hi | 0.315 | 0.314 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 3-of-6 | P | 0.149 | 0.148 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 3-of-6 | P_crowd_lo | 0.21 | 0.211 | +0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 4-of-6 | F1 | 0.365 | 0.364 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 4-of-6 | F1_hi | 0.446 | 0.445 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 4-of-6 | P | 0.269 | 0.268 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 4-of-6 | P_crowd | 0.417 | 0.416 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 4-of-6 | P_crowd_hi | 0.523 | 0.522 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 4-of-6 | P_crowd_lo | 0.324 | 0.323 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 4-of-6 | P_hi | 0.357 | 0.355 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 4-of-6 | P_lo | 0.182 | 0.181 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 4-of-6 | R | 0.568 | 0.566 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 4-of-6 | R_hi | 0.655 | 0.654 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 4-of-6 | R_lo | 0.475 | 0.472 | -0.003 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 5-of-6 | F1 | 0.392 | 0.388 | -0.004 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 5-of-6 | F1_hi | 0.473 | 0.47 | -0.003 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 5-of-6 | F1_lo | 0.288 | 0.282 | -0.006 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 5-of-6 | P | 0.477 | 0.474 | -0.003 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 5-of-6 | P_crowd | 0.639 | 0.636 | -0.003 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 5-of-6 | P_crowd_hi | 0.777 | 0.774 | -0.003 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 5-of-6 | P_crowd_lo | 0.48 | 0.478 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 5-of-6 | P_hi | 0.583 | 0.579 | -0.004 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 5-of-6 | P_lo | 0.351 | 0.348 | -0.003 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 5-of-6 | R | 0.333 | 0.329 | -0.004 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 5-of-6 | R_hi | 0.431 | 0.43 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 5-of-6 | R_lo | 0.227 | 0.223 | -0.004 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 6-of-6 | F1 | 0.25 | 0.251 | +0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 6-of-6 | F1_lo | 0.16 | 0.162 | +0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 6-of-6 | P | 0.793 | 0.791 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 6-of-6 | P_crowd_lo | 0.897 | 0.896 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | 6-of-6 | P_lo | 0.724 | 0.722 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | MS | P_crowd_lo | 0.214 | 0.213 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UH | F1 | 0.197 | 0.195 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UH | F1_hi | 0.277 | 0.275 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UH | F1_lo | 0.122 | 0.12 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UH | P | 0.126 | 0.124 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UH | P_crowd | 0.202 | 0.201 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UH | P_crowd_hi | 0.294 | 0.293 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UH | P_crowd_lo | 0.13 | 0.129 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UH | P_hi | 0.197 | 0.195 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UH | P_lo | 0.072 | 0.071 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UH | R_hi | 0.542 | 0.543 | +0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UNEP | F1 | 0.185 | 0.184 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UNEP | F1_hi | 0.271 | 0.269 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UNEP | F1_lo | 0.108 | 0.107 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UNEP | P_crowd | 0.254 | 0.253 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UNEP | P_crowd_hi | 0.321 | 0.32 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UNEP | P_hi | 0.188 | 0.186 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UNEP | P_lo | 0.063 | 0.062 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UNEP | R | 0.436 | 0.431 | -0.005 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UNEP | R_hi | 0.538 | 0.534 | -0.004 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 10.0 | UNEP | R_lo | 0.34 | 0.335 | -0.005 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 1-of-6 | F1_lo | 0.12 | 0.119 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 2-of-6 | F1_hi | 0.321 | 0.32 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 3-of-6 | F1_hi | 0.458 | 0.457 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 3-of-6 | P_hi | 0.31 | 0.309 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 3-of-6 | P_lo | 0.169 | 0.168 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 4-of-6 | F1 | 0.485 | 0.484 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 4-of-6 | F1_lo | 0.358 | 0.357 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 4-of-6 | P_hi | 0.507 | 0.506 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 4-of-6 | R | 0.654 | 0.653 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 4-of-6 | R_hi | 0.728 | 0.727 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 4-of-6 | R_lo | 0.567 | 0.564 | -0.003 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 5-of-6 | F1 | 0.487 | 0.481 | -0.006 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 5-of-6 | F1_hi | 0.586 | 0.581 | -0.005 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 5-of-6 | F1_lo | 0.359 | 0.355 | -0.004 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 5-of-6 | P | 0.616 | 0.612 | -0.004 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 5-of-6 | P_hi | 0.748 | 0.742 | -0.006 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 5-of-6 | P_lo | 0.439 | 0.436 | -0.003 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 5-of-6 | R | 0.402 | 0.397 | -0.005 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 5-of-6 | R_hi | 0.515 | 0.509 | -0.006 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 5-of-6 | R_lo | 0.287 | 0.282 | -0.005 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 6-of-6 | F1_hi | 0.411 | 0.412 | +0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 6-of-6 | P | 0.939 | 0.938 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | 6-of-6 | P_lo | 0.899 | 0.898 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | UH | F1 | 0.267 | 0.265 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | UH | F1_hi | 0.366 | 0.364 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | UH | F1_lo | 0.171 | 0.169 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | UH | P | 0.182 | 0.18 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | UH | P_hi | 0.28 | 0.279 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | UH | P_lo | 0.105 | 0.104 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | UNEP | P | 0.17 | 0.171 | +0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | UNEP | R | 0.542 | 0.541 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | UNEP | R_hi | 0.642 | 0.641 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 20.0 | UNEP | R_lo | 0.443 | 0.442 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 1-of-6 | visits_per_find | 25.79 | 25.81 | +0.020 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 1-of-6 | visits_per_find_hi | 39.51 | 39.54 | +0.030 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 1-of-6 | visits_per_find_lo | 18.67 | 18.68 | +0.010 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 2-of-6 | F1_lo | 0.256 | 0.255 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 2-of-6 | visits_per_find | 14.67 | 14.69 | +0.020 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 2-of-6 | visits_per_find_hi | 21.55 | 21.58 | +0.030 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 2-of-6 | visits_per_find_lo | 10.97 | 10.98 | +0.010 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 3-of-6 | F1 | 0.473 | 0.472 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 3-of-6 | F1_lo | 0.366 | 0.365 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 3-of-6 | visits_per_find | 6.99 | 7 | +0.010 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 3-of-6 | visits_per_find_hi | 9.92 | 9.95 | +0.030 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 3-of-6 | visits_per_find_lo | 5.29 | 5.31 | +0.020 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 4-of-6 | F1_hi | 0.665 | 0.664 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 4-of-6 | F1_lo | 0.424 | 0.423 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 4-of-6 | P | 0.462 | 0.461 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 4-of-6 | P_hi | 0.603 | 0.601 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 4-of-6 | visits_per_find | 2.95 | 2.96 | +0.010 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 4-of-6 | visits_per_find_hi | 4.22 | 4.24 | +0.020 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 4-of-6 | visits_per_find_lo | 2.14 | 2.15 | +0.010 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 5-of-6 | F1 | 0.552 | 0.548 | -0.004 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 5-of-6 | F1_hi | 0.652 | 0.649 | -0.003 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 5-of-6 | F1_lo | 0.42 | 0.417 | -0.003 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 5-of-6 | P | 0.683 | 0.681 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 5-of-6 | P_hi | 0.824 | 0.823 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 5-of-6 | P_lo | 0.489 | 0.487 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 5-of-6 | R | 0.464 | 0.459 | -0.005 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 5-of-6 | R_hi | 0.581 | 0.577 | -0.004 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 5-of-6 | R_lo | 0.344 | 0.34 | -0.004 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 5-of-6 | visits_per_find | 1.34 | 1.36 | +0.020 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 5-of-6 | visits_per_find_hi | 1.73 | 1.75 | +0.020 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 5-of-6 | visits_per_find_lo | 1.01 | 1.03 | +0.020 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 6-of-6 | P | 0.977 | 0.976 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 6-of-6 | P_lo | 0.947 | 0.946 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | 6-of-6 | visits_per_find_hi | 0.8 | 0.79 | -0.010 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | MS | visits_per_find_hi | 11.07 | 11.08 | +0.010 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | UH | F1 | 0.321 | 0.319 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | UH | F1_hi | 0.429 | 0.428 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | UH | F1_lo | 0.214 | 0.211 | -0.003 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | UH | P | 0.225 | 0.222 | -0.003 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | UH | P_hi | 0.341 | 0.34 | -0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | UH | P_lo | 0.134 | 0.132 | -0.002 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | UH | R | 0.562 | 0.563 | +0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | UH | R_hi | 0.662 | 0.663 | +0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | UH | R_lo | 0.464 | 0.465 | +0.001 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | UH | visits_per_find | 6.5 | 6.59 | +0.090 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | UH | visits_per_find_hi | 11.16 | 11.34 | +0.180 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | UH | visits_per_find_lo | 4.16 | 4.19 | +0.030 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci | 30.0 | UNEP | visits_per_find_hi | 10.34 | 10.36 | +0.020 | RQ9-uncertainty/rq9_ci_core.csv |
| core | ci-labels | 10.0 | MS (as shipped) | P_hi | 0.179 | 0.18 | +0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | MS (as shipped) | R | 0.464 | 0.465 | +0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | MS (as shipped) | R_hi | 0.574 | 0.576 | +0.002 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UH (as shipped) | F1 | 0.182 | 0.18 | -0.002 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UH (as shipped) | F1_hi | 0.258 | 0.256 | -0.002 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UH (as shipped) | F1_lo | 0.118 | 0.117 | -0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UH (as shipped) | P | 0.126 | 0.124 | -0.002 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UH (as shipped) | P_hi | 0.205 | 0.203 | -0.002 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UH (as shipped) | P_lo | 0.074 | 0.073 | -0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UH (as shipped) − null (logit) | F1_diff | 0.009 | 0.007 | -0.002 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UH (as shipped) − null (logit) | F1_diff_hi | 0.068 | 0.067 | -0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UH (as shipped) − null (logit) | F1_diff_lo | -0.041 | -0.043 | -0.002 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UNEP (as shipped) | F1 | 0.172 | 0.171 | -0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UNEP (as shipped) | F1_hi | 0.25 | 0.248 | -0.002 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UNEP (as shipped) | P_hi | 0.187 | 0.185 | -0.002 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UNEP (as shipped) | P_lo | 0.067 | 0.066 | -0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UNEP (as shipped) | R | 0.319 | 0.317 | -0.002 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UNEP (as shipped) | R_hi | 0.414 | 0.412 | -0.002 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UNEP (as shipped) | R_lo | 0.229 | 0.228 | -0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UNEP (as shipped) − null (logit) | F1_diff | -0.004 | -0.005 | -0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UNEP (as shipped) − null (logit) | F1_diff_hi | 0.065 | 0.063 | -0.002 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | UNEP (as shipped) − null (logit) | F1_diff_lo | -0.057 | -0.058 | -0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | flat k-of-6 voting | F1 | 0.324 | 0.323 | -0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | flat k-of-6 voting | F1_hi | 0.4 | 0.399 | -0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | flat k-of-6 voting | F1_lo | 0.234 | 0.233 | -0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | flat k-of-6 voting | P | 0.269 | 0.268 | -0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | flat k-of-6 voting | P_hi | 0.356 | 0.354 | -0.002 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | flat k-of-6 voting − null (logit) | F1_diff | 0.148 | 0.147 | -0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | flat k-of-6 voting − null (logit) | F1_diff_hi | 0.213 | 0.212 | -0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | weighted fusion | F1 | 0.374 | 0.371 | -0.003 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | weighted fusion | F1_hi | 0.434 | 0.433 | -0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | weighted fusion | F1_lo | 0.295 | 0.289 | -0.006 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | weighted fusion | P | 0.358 | 0.37 | +0.012 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | weighted fusion | P_hi | 0.434 | 0.448 | +0.014 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | weighted fusion | P_lo | 0.268 | 0.276 | +0.008 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | weighted fusion | R | 0.39 | 0.372 | -0.018 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | weighted fusion | R_hi | 0.476 | 0.461 | -0.015 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | weighted fusion | R_lo | 0.298 | 0.28 | -0.018 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | weighted fusion − null (logit) | F1_diff | 0.197 | 0.194 | -0.003 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | weighted fusion − null (logit) | F1_diff_hi | 0.249 | 0.25 | +0.001 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| core | ci-labels | 10.0 | weighted fusion − null (logit) | F1_diff_lo | 0.145 | 0.139 | -0.006 | RQ9-uncertainty/rq9_ci_models_r10.csv |
| Caraballeda | cells | 8.0 | UH | delta | -0.204 | -0.207 | -0.003 | pipeline/ranking.py |
| Caraballeda | cells | 8.0 | UH | rho | 0.388 | 0.384 | -0.004 | pipeline/ranking.py |
| Caraballeda | cells | 8.0 | UNEP | cells | 122 | 123 | +1.000 | pipeline/ranking.py |
| Caraballeda | cells | 8.0 | UNEP | delta | -0.066 | -0.058 | +0.008 | pipeline/ranking.py |
| Caraballeda | cells | 8.0 | UNEP | rho | 0.451 | 0.463 | +0.012 | pipeline/ranking.py |
| Caraballeda | cells | 8.0 | UNEP | rho_null | 0.516 | 0.52 | +0.004 | pipeline/ranking.py |
| Caraballeda | cells | 9.0 | UH | delta | -0.284 | -0.286 | -0.002 | pipeline/ranking.py |
| Caraballeda | cells | 9.0 | UH | rho | 0.13 | 0.128 | -0.002 | pipeline/ranking.py |
| Caraballeda | cells | 9.0 | UNEP | cells | 414 | 415 | +1.000 | pipeline/ranking.py |
| Caraballeda | cells | 9.0 | UNEP | delta | -0.11 | -0.106 | +0.004 | pipeline/ranking.py |
| Caraballeda | cells | 9.0 | UNEP | rho | 0.207 | 0.212 | +0.005 | pipeline/ranking.py |
| Caraballeda | cells | 9.0 | UNEP | rho_null | 0.317 | 0.318 | +0.001 | pipeline/ranking.py |
| asd | cells | 7.0 | UH | cells | 106 | 107 | +1.000 | pipeline/ranking.py |
| asd | cells | 7.0 | UH | delta | -0.783 | -0.77 | +0.013 | pipeline/ranking.py |
| asd | cells | 7.0 | UH | rho | -0.085 | -0.073 | +0.012 | pipeline/ranking.py |
| asd | cells | 7.0 | UH | rho_null | 0.698 | 0.696 | -0.002 | pipeline/ranking.py |
| asd | cells | 7.0 | UNEP | delta | -0.279 | -0.276 | +0.003 | pipeline/ranking.py |
| asd | cells | 7.0 | UNEP | rho | 0.219 | 0.222 | +0.003 | pipeline/ranking.py |
| asd | cells | 8.0 | UH | cells | 453 | 454 | +1.000 | pipeline/ranking.py |
| asd | cells | 8.0 | UNEP | cells | 601 | 602 | +1.000 | pipeline/ranking.py |
| asd | cells | 8.0 | UNEP | delta | -0.382 | -0.378 | +0.004 | pipeline/ranking.py |
| asd | cells | 8.0 | UNEP | rho | 0.068 | 0.071 | +0.003 | pipeline/ranking.py |
| core | cells | 8.0 | UH | delta | -0.164 | -0.167 | -0.003 | pipeline/ranking.py |
| core | cells | 8.0 | UH | rho | 0.48 | 0.477 | -0.003 | pipeline/ranking.py |
| core | cells | 8.0 | UNEP | delta | -0.067 | -0.066 | +0.001 | pipeline/ranking.py |
| core | cells | 8.0 | UNEP | rho | 0.577 | 0.579 | +0.002 | pipeline/ranking.py |
| core | cells | 9.0 | UH | delta | -0.167 | -0.168 | -0.001 | pipeline/ranking.py |
| core | cells | 9.0 | UH | rho | 0.304 | 0.303 | -0.001 | pipeline/ranking.py |
| core | cells | 9.0 | UNEP | delta | -0.028 | -0.025 | +0.003 | pipeline/ranking.py |
| core | cells | 9.0 | UNEP | rho | 0.443 | 0.445 | +0.002 | pipeline/ranking.py |
| core | cells-agreement | 8.0 | 1-of-6 | rho_frac | 0.659 | 0.655 | -0.004 | pipeline/ranking.py |
| core | cells-agreement | 8.0 | 2-of-6 | rho_frac | 0.742 | 0.741 | -0.001 | pipeline/ranking.py |
| core | cells-agreement | 8.0 | 4-of-6 | rho | 0.781 | 0.783 | +0.002 | pipeline/ranking.py |
| core | cells-agreement | 8.0 | 4-of-6 | rho_frac | 0.73 | 0.732 | +0.002 | pipeline/ranking.py |
| core | cells-agreement | 8.0 | 5-of-6 | rho | 0.687 | 0.684 | -0.003 | pipeline/ranking.py |
| core | cells-agreement | 8.0 | 5-of-6 | rho_frac | 0.638 | 0.637 | -0.001 | pipeline/ranking.py |
| core | cells-agreement | 8.0 | Microsoft | rho_frac | 0.444 | 0.443 | -0.001 | pipeline/ranking.py |
| core | cells-agreement | 8.0 | UH | rho | 0.48 | 0.477 | -0.003 | pipeline/ranking.py |
| core | cells-agreement | 8.0 | UH | rho_frac | 0.241 | 0.24 | -0.001 | pipeline/ranking.py |
| core | cells-agreement | 8.0 | UNEP | rho | 0.577 | 0.579 | +0.002 | pipeline/ranking.py |
| core | cells-agreement | 8.0 | UNEP | rho_frac | 0.389 | 0.384 | -0.005 | pipeline/ranking.py |
| core | cells-agreement | 8.0 | vote sum | rho_frac | 0.727 | 0.726 | -0.001 | pipeline/ranking.py |
| core | cells-agreement | 9.0 | 1-of-6 | rho_frac | 0.554 | 0.553 | -0.001 | pipeline/ranking.py |
| core | cells-agreement | 9.0 | 4-of-6 | rho | 0.652 | 0.656 | +0.004 | pipeline/ranking.py |
| core | cells-agreement | 9.0 | 4-of-6 | rho_frac | 0.649 | 0.656 | +0.007 | pipeline/ranking.py |
| core | cells-agreement | 9.0 | 5-of-6 | rho | 0.595 | 0.592 | -0.003 | pipeline/ranking.py |
| core | cells-agreement | 9.0 | 5-of-6 | rho_frac | 0.585 | 0.583 | -0.002 | pipeline/ranking.py |
| core | cells-agreement | 9.0 | UH | rho | 0.304 | 0.303 | -0.001 | pipeline/ranking.py |
| core | cells-agreement | 9.0 | UH | rho_frac | 0.21 | 0.208 | -0.002 | pipeline/ranking.py |
| core | cells-agreement | 9.0 | UNEP | rho | 0.443 | 0.445 | +0.002 | pipeline/ranking.py |
| core | cells-agreement | 9.0 | UNEP | rho_frac | 0.366 | 0.372 | +0.006 | pipeline/ranking.py |
| core | cells-agreement | 9.0 | vote sum | rho_frac | 0.623 | 0.622 | -0.001 | pipeline/ranking.py |
| Caraballeda | crowd | 10.0 | IMPACT | crowd_cov | 0.46 | 0.45 | -0.010 | pipeline/scorecards.py |
| Caraballeda | crowd | 10.0 | IMPACT | fp_crowd_damaged | 0.09 | 0.19 | +0.100 | pipeline/scorecards.py |
| Caraballeda | crowd | 10.0 | LIST | fp_crowd_damaged | 0.08 | 0.19 | +0.110 | pipeline/scorecards.py |
| Caraballeda | crowd | 10.0 | OSU | fp_crowd_damaged | 0.08 | 0.19 | +0.110 | pipeline/scorecards.py |
| Caraballeda | crowd | 10.0 | UH | P_crowd | 0.202 | 0.2 | -0.002 | pipeline/scorecards.py |
| Caraballeda | crowd | 10.0 | UH | fp_crowd_damaged | 0.09 | 0.34 | +0.250 | pipeline/scorecards.py |
| Caraballeda | crowd | 10.0 | UNEP | P_crowd | 0.25 | 0.249 | -0.001 | pipeline/scorecards.py |
| Caraballeda | crowd | 10.0 | UNEP | fp_crowd_damaged | 0.15 | 0.17 | +0.020 | pipeline/scorecards.py |
| Caraballeda | points | 10.0 | MS | n_flags | 7944 | 7950 | +6.000 | pipeline/scorecards.py |
| Caraballeda | points | 10.0 | UH | P | 0.126 | 0.124 | -0.002 | pipeline/scorecards.py |
| Caraballeda | points | 10.0 | UH | flag_share | 0.094 | 0.095 | +0.001 | pipeline/scorecards.py |
| Caraballeda | points | 10.0 | UH | n_flags | 5366 | 5447 | +81.000 | pipeline/scorecards.py |
| Caraballeda | points | 10.0 | UNEP | P | 0.116 | 0.115 | -0.001 | pipeline/scorecards.py |
| Caraballeda | points | 10.0 | UNEP | R | 0.435 | 0.431 | -0.004 | pipeline/scorecards.py |
| Caraballeda | points | 10.0 | UNEP | n_flags | 5689 | 5693 | +4.000 | pipeline/scorecards.py |
| Caracas | crowd | 10.0 | UH | fp_crowd_damaged | 0 | 0.12 | +0.120 | pipeline/scorecards.py |
| Caracas | points | 10.0 | UH | flag_share | 0.177 | 0.18 | +0.003 | pipeline/scorecards.py |
| Caracas | points | 10.0 | UH | n_flags | 18176 | 18452 | +276.000 | pipeline/scorecards.py |
| Caracas | points | 10.0 | UNEP | n_flags | 5495 | 5509 | +14.000 | pipeline/scorecards.py |
| Moron | crowd | 10.0 | IMPACT | fp_crowd_damaged | 0.01 | 0.48 | +0.470 | pipeline/scorecards.py |
| Moron | crowd | 10.0 | LIST | fp_crowd_damaged | 0.02 | 0.35 | +0.330 | pipeline/scorecards.py |
| Moron | crowd | 10.0 | OSU | fp_crowd_damaged | 0.04 | 0.34 | +0.300 | pipeline/scorecards.py |
| Moron | crowd | 10.0 | UH | fp_crowd_damaged | 0 | 0.14 | +0.140 | pipeline/scorecards.py |
| Moron | crowd | 10.0 | UNEP | fp_crowd_damaged | 0.04 | 0.35 | +0.310 | pipeline/scorecards.py |
| Moron | points | 10.0 | UNEP | n_flags | 583 | 584 | +1.000 | pipeline/scorecards.py |
| San Felipe | points | 10.0 | UNEP | n_flags | 1039 | 1044 | +5.000 | pipeline/scorecards.py |
| Santa Cruz | points | 10.0 | UH | n_flags | 32145 | 32144 | -1.000 | pipeline/scorecards.py |
| Santa Cruz | points | 10.0 | UNEP | n_flags | 5073 | 5107 | +34.000 | pipeline/scorecards.py |
| all | flags | nan | MS | in_cems_extent | 7944 | 7950 | +6.000 | pipeline/scorecards.py |
| all | flags | nan | MS | total_flags | 8332 | 8338 | +6.000 | pipeline/scorecards.py |
| all | flags | nan | UH | in_cems_extent | 55952 | 56308 | +356.000 | pipeline/scorecards.py |
| all | flags | nan | UH | share_outside | 0.251 | 0.25 | -0.001 | pipeline/scorecards.py |
| all | flags | nan | UH | total_flags | 74705 | 75118 | +413.000 | pipeline/scorecards.py |
| all | flags | nan | UNEP | in_cems_extent | 17879 | 17937 | +58.000 | pipeline/scorecards.py |
| all | flags | nan | UNEP | share_outside | 0.763 | 0.76 | -0.003 | pipeline/scorecards.py |
| all | flags | nan | UNEP | total_flags | 75476 | 74867 | -609.000 | pipeline/scorecards.py |
| asd | crowd | 10.0 | IMPACT | fp_crowd_damaged | 0.04 | 0.19 | +0.150 | pipeline/scorecards.py |
| asd | crowd | 10.0 | LIST | fp_crowd_damaged | 0.04 | 0.19 | +0.150 | pipeline/scorecards.py |
| asd | crowd | 10.0 | OSU | fp_crowd_damaged | 0.06 | 0.19 | +0.130 | pipeline/scorecards.py |
| asd | crowd | 10.0 | UH | fp_crowd_damaged | 0.01 | 0.34 | +0.330 | pipeline/scorecards.py |
| asd | crowd | 10.0 | UNEP | fp_crowd_damaged | 0.05 | 0.18 | +0.130 | pipeline/scorecards.py |
| asd | points | 10.0 | MS | n_flags | 7944 | 7950 | +6.000 | pipeline/scorecards.py |
| asd | points | 10.0 | UH | R | 0.45 | 0.451 | +0.001 | pipeline/scorecards.py |
| asd | points | 10.0 | UH | flag_share | 0.193 | 0.194 | +0.001 | pipeline/scorecards.py |
| asd | points | 10.0 | UH | n_flags | 55952 | 56308 | +356.000 | pipeline/scorecards.py |
| asd | points | 10.0 | UNEP | R | 0.425 | 0.421 | -0.004 | pipeline/scorecards.py |
| asd | points | 10.0 | UNEP | n_flags | 17879 | 17937 | +58.000 | pipeline/scorecards.py |
| core | bounds | 10.0 | UH | P_crowd | 0.202 | 0.201 | -0.001 | pipeline/scorecards.py |
| core | bounds | 10.0 | UH | P_floor | 0.126 | 0.124 | -0.002 | pipeline/scorecards.py |
| core | bounds | 10.0 | UH | P_grade | 0.171 | 0.169 | -0.002 | pipeline/scorecards.py |
| core | bounds | 10.0 | UH | P_upper | 0.232 | 0.23 | -0.002 | pipeline/scorecards.py |
| core | bounds | 10.0 | UNEP | P_crowd | 0.254 | 0.253 | -0.001 | pipeline/scorecards.py |
| core | bounds | 10.0 | UNEP | P_grade | 0.179 | 0.178 | -0.001 | pipeline/scorecards.py |
| core | bounds | 10.0 | UNEP | P_upper | 0.296 | 0.295 | -0.001 | pipeline/scorecards.py |
| core | crowd | 10.0 | 4-of-6 | P_crowd | 0.417 | 0.416 | -0.001 | pipeline/scorecards.py |
| core | crowd | 10.0 | 5-of-6 | P_crowd | 0.639 | 0.636 | -0.003 | pipeline/scorecards.py |
| core | crowd | 10.0 | LIST∧UH | P_crowd | 0.388 | 0.386 | -0.002 | pipeline/scorecards.py |
| core | crowd | 10.0 | LIST∧UH | crowd_cov | 0.38 | 0.37 | -0.010 | pipeline/scorecards.py |
| core | crowd | 10.0 | MS∧LIST | P_crowd | 0.382 | 0.381 | -0.001 | pipeline/scorecards.py |
| core | crowd | 10.0 | MS∧UNEP | P_crowd | 0.311 | 0.309 | -0.002 | pipeline/scorecards.py |
| core | crowd | 10.0 | UH | P_crowd | 0.202 | 0.201 | -0.001 | pipeline/scorecards.py |
| core | crowd | 10.0 | UNEP | P_crowd | 0.254 | 0.253 | -0.001 | pipeline/scorecards.py |
| core | crowd | 10.0 | UNEP∧OSU | P_crowd | 0.324 | 0.323 | -0.001 | pipeline/scorecards.py |
| core | field-union | 10.0 | UH | P_cems | 0.126 | 0.124 | -0.002 | pipeline/scorecards.py |
| core | field-union | 10.0 | UH | P_union | 0.13 | 0.128 | -0.002 | pipeline/scorecards.py |
| core | field-union | 10.0 | UH | R_union | 0.472 | 0.473 | +0.001 | pipeline/scorecards.py |
| core | field-union | 10.0 | UNEP | P_union | 0.122 | 0.121 | -0.001 | pipeline/scorecards.py |
| core | field-union | 10.0 | UNEP | R_cems | 0.436 | 0.431 | -0.005 | pipeline/scorecards.py |
| core | field-union | 10.0 | UNEP | R_union | 0.467 | 0.463 | -0.004 | pipeline/scorecards.py |
| core | grade-recall | 10.0 | UH | P_vs_damaged | 0.058 | 0.057 | -0.001 | pipeline/scorecards.py |
| core | grade-recall | 10.0 | UH | P_vs_destroyed | 0.086 | 0.085 | -0.001 | pipeline/scorecards.py |
| core | grade-recall | 10.0 | UH | R_of_destroyed | 0.584 | 0.586 | +0.002 | pipeline/scorecards.py |
| core | grade-recall | 10.0 | UNEP | P_vs_destroyed | 0.081 | 0.08 | -0.001 | pipeline/scorecards.py |
| core | grade-recall | 10.0 | UNEP | R_of_damaged | 0.282 | 0.281 | -0.001 | pipeline/scorecards.py |
| core | grade-recall | 10.0 | UNEP | R_of_destroyed | 0.612 | 0.605 | -0.007 | pipeline/scorecards.py |
| core | points | 10.0 | 1-of-6 | n_flags | 37316 | 37346 | +30.000 | pipeline/scorecards.py |
| core | points | 10.0 | 2-of-6 | n_flags | 20742 | 20766 | +24.000 | pipeline/scorecards.py |
| core | points | 10.0 | 3-of-6 | P | 0.149 | 0.148 | -0.001 | pipeline/scorecards.py |
| core | points | 10.0 | 3-of-6 | n_flags | 9116 | 9140 | +24.000 | pipeline/scorecards.py |
| core | points | 10.0 | 4-of-6 | F1 | 0.365 | 0.364 | -0.001 | pipeline/scorecards.py |
| core | points | 10.0 | 4-of-6 | P | 0.269 | 0.268 | -0.001 | pipeline/scorecards.py |
| core | points | 10.0 | 4-of-6 | R | 0.568 | 0.566 | -0.002 | pipeline/scorecards.py |
| core | points | 10.0 | 4-of-6 | n_flags | 3114 | 3123 | +9.000 | pipeline/scorecards.py |
| core | points | 10.0 | 5-of-6 | F1 | 0.392 | 0.388 | -0.004 | pipeline/scorecards.py |
| core | points | 10.0 | 5-of-6 | P | 0.477 | 0.474 | -0.003 | pipeline/scorecards.py |
| core | points | 10.0 | 5-of-6 | R | 0.333 | 0.329 | -0.004 | pipeline/scorecards.py |
| core | points | 10.0 | 5-of-6 | n_flags | 912 | 915 | +3.000 | pipeline/scorecards.py |
| core | points | 10.0 | 6-of-6 | F1 | 0.25 | 0.251 | +0.001 | pipeline/scorecards.py |
| core | points | 10.0 | 6-of-6 | P | 0.793 | 0.791 | -0.002 | pipeline/scorecards.py |
| core | points | 10.0 | 6-of-6 | n_flags | 213 | 211 | -2.000 | pipeline/scorecards.py |
| core | points | 10.0 | LIST∧UH | F1 | 0.311 | 0.31 | -0.001 | pipeline/scorecards.py |
| core | points | 10.0 | LIST∧UH | P | 0.27 | 0.267 | -0.003 | pipeline/scorecards.py |
| core | points | 10.0 | LIST∧UH | R | 0.368 | 0.369 | +0.001 | pipeline/scorecards.py |
| core | points | 10.0 | LIST∧UH | n_flags | 1825 | 1848 | +23.000 | pipeline/scorecards.py |
| core | points | 10.0 | MS | n_flags | 7872 | 7878 | +6.000 | pipeline/scorecards.py |
| core | points | 10.0 | MS∧LIST | P | 0.226 | 0.225 | -0.001 | pipeline/scorecards.py |
| core | points | 10.0 | MS∧LIST | n_flags | 2875 | 2879 | +4.000 | pipeline/scorecards.py |
| core | points | 10.0 | MS∧UH | P | 0.483 | 0.482 | -0.001 | pipeline/scorecards.py |
| core | points | 10.0 | MS∧UH | R | 0.346 | 0.347 | +0.001 | pipeline/scorecards.py |
| core | points | 10.0 | MS∧UH | n_flags | 965 | 969 | +4.000 | pipeline/scorecards.py |
| core | points | 10.0 | MS∧UNEP | F1 | 0.226 | 0.224 | -0.002 | pipeline/scorecards.py |
| core | points | 10.0 | MS∧UNEP | P | 0.163 | 0.162 | -0.001 | pipeline/scorecards.py |
| core | points | 10.0 | MS∧UNEP | R | 0.367 | 0.363 | -0.004 | pipeline/scorecards.py |
| core | points | 10.0 | MS∧UNEP | R_field20 | 0.59 | 0.58 | -0.010 | pipeline/scorecards.py |
| core | points | 10.0 | MS∧UNEP | n_flags | 3172 | 3185 | +13.000 | pipeline/scorecards.py |
| core | points | 10.0 | UH | F1 | 0.197 | 0.195 | -0.002 | pipeline/scorecards.py |
| core | points | 10.0 | UH | P | 0.126 | 0.124 | -0.002 | pipeline/scorecards.py |
| core | points | 10.0 | UH | n_flags | 5362 | 5443 | +81.000 | pipeline/scorecards.py |
| core | points | 10.0 | UNEP | F1 | 0.185 | 0.184 | -0.001 | pipeline/scorecards.py |
| core | points | 10.0 | UNEP | R | 0.436 | 0.431 | -0.005 | pipeline/scorecards.py |
| core | points | 10.0 | UNEP | n_flags | 5604 | 5605 | +1.000 | pipeline/scorecards.py |
| core | points | 10.0 | UNEP∧OSU | F1 | 0.251 | 0.25 | -0.001 | pipeline/scorecards.py |
| core | points | 10.0 | UNEP∧OSU | P | 0.181 | 0.18 | -0.001 | pipeline/scorecards.py |
| core | points | 10.0 | UNEP∧OSU | R | 0.413 | 0.41 | -0.003 | pipeline/scorecards.py |
| core | points | 10.0 | UNEP∧OSU | n_flags | 3391 | 3389 | -2.000 | pipeline/scorecards.py |
| core | points | 20.0 | 1-of-6 | n_flags | 37316 | 37346 | +30.000 | pipeline/scorecards.py |
| core | points | 20.0 | 2-of-6 | n_flags | 20742 | 20766 | +24.000 | pipeline/scorecards.py |
| core | points | 20.0 | 3-of-6 | n_flags | 9116 | 9140 | +24.000 | pipeline/scorecards.py |
| core | points | 20.0 | 4-of-6 | F1 | 0.485 | 0.484 | -0.001 | pipeline/scorecards.py |
| core | points | 20.0 | 4-of-6 | R | 0.654 | 0.653 | -0.001 | pipeline/scorecards.py |
| core | points | 20.0 | 4-of-6 | n_flags | 3114 | 3123 | +9.000 | pipeline/scorecards.py |
| core | points | 20.0 | 5-of-6 | F1 | 0.487 | 0.481 | -0.006 | pipeline/scorecards.py |
| core | points | 20.0 | 5-of-6 | P | 0.616 | 0.612 | -0.004 | pipeline/scorecards.py |
| core | points | 20.0 | 5-of-6 | R | 0.402 | 0.397 | -0.005 | pipeline/scorecards.py |
| core | points | 20.0 | 5-of-6 | n_flags | 912 | 915 | +3.000 | pipeline/scorecards.py |
| core | points | 20.0 | 6-of-6 | P | 0.939 | 0.938 | -0.001 | pipeline/scorecards.py |
| core | points | 20.0 | 6-of-6 | n_flags | 213 | 211 | -2.000 | pipeline/scorecards.py |
| core | points | 20.0 | LIST∧UH | F1 | 0.404 | 0.402 | -0.002 | pipeline/scorecards.py |
| core | points | 20.0 | LIST∧UH | P | 0.374 | 0.37 | -0.004 | pipeline/scorecards.py |
| core | points | 20.0 | LIST∧UH | n_flags | 1825 | 1848 | +23.000 | pipeline/scorecards.py |
| core | points | 20.0 | MS | n_flags | 7872 | 7878 | +6.000 | pipeline/scorecards.py |
| core | points | 20.0 | MS∧LIST | n_flags | 2875 | 2879 | +4.000 | pipeline/scorecards.py |
| core | points | 20.0 | MS∧UH | F1 | 0.479 | 0.478 | -0.001 | pipeline/scorecards.py |
| core | points | 20.0 | MS∧UH | P | 0.622 | 0.62 | -0.002 | pipeline/scorecards.py |
| core | points | 20.0 | MS∧UH | n_flags | 965 | 969 | +4.000 | pipeline/scorecards.py |
| core | points | 20.0 | MS∧UNEP | F1 | 0.294 | 0.291 | -0.003 | pipeline/scorecards.py |
| core | points | 20.0 | MS∧UNEP | P | 0.218 | 0.217 | -0.001 | pipeline/scorecards.py |
| core | points | 20.0 | MS∧UNEP | R | 0.448 | 0.443 | -0.005 | pipeline/scorecards.py |
| core | points | 20.0 | MS∧UNEP | R_field20 | 0.59 | 0.58 | -0.010 | pipeline/scorecards.py |
| core | points | 20.0 | MS∧UNEP | n_flags | 3172 | 3185 | +13.000 | pipeline/scorecards.py |
| core | points | 20.0 | UH | F1 | 0.267 | 0.265 | -0.002 | pipeline/scorecards.py |
| core | points | 20.0 | UH | P | 0.182 | 0.18 | -0.002 | pipeline/scorecards.py |
| core | points | 20.0 | UH | n_flags | 5362 | 5443 | +81.000 | pipeline/scorecards.py |
| core | points | 20.0 | UNEP | P | 0.17 | 0.171 | +0.001 | pipeline/scorecards.py |
| core | points | 20.0 | UNEP | R | 0.542 | 0.541 | -0.001 | pipeline/scorecards.py |
| core | points | 20.0 | UNEP | n_flags | 5604 | 5605 | +1.000 | pipeline/scorecards.py |
| core | points | 20.0 | UNEP∧OSU | F1 | 0.339 | 0.34 | +0.001 | pipeline/scorecards.py |
| core | points | 20.0 | UNEP∧OSU | P | 0.254 | 0.255 | +0.001 | pipeline/scorecards.py |
| core | points | 20.0 | UNEP∧OSU | n_flags | 3391 | 3389 | -2.000 | pipeline/scorecards.py |
| core | points | 30.0 | 1-of-6 | n_flags | 37316 | 37346 | +30.000 | pipeline/scorecards.py |
| core | points | 30.0 | 2-of-6 | n_flags | 20742 | 20766 | +24.000 | pipeline/scorecards.py |
| core | points | 30.0 | 3-of-6 | F1 | 0.473 | 0.472 | -0.001 | pipeline/scorecards.py |
| core | points | 30.0 | 3-of-6 | n_flags | 9116 | 9140 | +24.000 | pipeline/scorecards.py |
| core | points | 30.0 | 4-of-6 | P | 0.462 | 0.461 | -0.001 | pipeline/scorecards.py |
| core | points | 30.0 | 4-of-6 | n_flags | 3114 | 3123 | +9.000 | pipeline/scorecards.py |
| core | points | 30.0 | 5-of-6 | F1 | 0.552 | 0.548 | -0.004 | pipeline/scorecards.py |
| core | points | 30.0 | 5-of-6 | P | 0.683 | 0.681 | -0.002 | pipeline/scorecards.py |
| core | points | 30.0 | 5-of-6 | R | 0.464 | 0.459 | -0.005 | pipeline/scorecards.py |
| core | points | 30.0 | 5-of-6 | n_flags | 912 | 915 | +3.000 | pipeline/scorecards.py |
| core | points | 30.0 | 6-of-6 | P | 0.977 | 0.976 | -0.001 | pipeline/scorecards.py |
| core | points | 30.0 | 6-of-6 | n_flags | 213 | 211 | -2.000 | pipeline/scorecards.py |
| core | points | 30.0 | LIST∧UH | F1 | 0.472 | 0.469 | -0.003 | pipeline/scorecards.py |
| core | points | 30.0 | LIST∧UH | P | 0.449 | 0.445 | -0.004 | pipeline/scorecards.py |
| core | points | 30.0 | LIST∧UH | n_flags | 1825 | 1848 | +23.000 | pipeline/scorecards.py |
| core | points | 30.0 | MS | n_flags | 7872 | 7878 | +6.000 | pipeline/scorecards.py |
| core | points | 30.0 | MS∧LIST | F1 | 0.485 | 0.484 | -0.001 | pipeline/scorecards.py |
| core | points | 30.0 | MS∧LIST | n_flags | 2875 | 2879 | +4.000 | pipeline/scorecards.py |
| core | points | 30.0 | MS∧UH | F1 | 0.535 | 0.534 | -0.001 | pipeline/scorecards.py |
| core | points | 30.0 | MS∧UH | P | 0.692 | 0.691 | -0.001 | pipeline/scorecards.py |
| core | points | 30.0 | MS∧UH | n_flags | 965 | 969 | +4.000 | pipeline/scorecards.py |
| core | points | 30.0 | MS∧UNEP | F1 | 0.345 | 0.343 | -0.002 | pipeline/scorecards.py |
| core | points | 30.0 | MS∧UNEP | P | 0.258 | 0.257 | -0.001 | pipeline/scorecards.py |
| core | points | 30.0 | MS∧UNEP | R | 0.521 | 0.516 | -0.005 | pipeline/scorecards.py |
| core | points | 30.0 | MS∧UNEP | R_field20 | 0.59 | 0.58 | -0.010 | pipeline/scorecards.py |
| core | points | 30.0 | MS∧UNEP | n_flags | 3172 | 3185 | +13.000 | pipeline/scorecards.py |
| core | points | 30.0 | UH | F1 | 0.321 | 0.319 | -0.002 | pipeline/scorecards.py |
| core | points | 30.0 | UH | P | 0.225 | 0.222 | -0.003 | pipeline/scorecards.py |
| core | points | 30.0 | UH | R | 0.562 | 0.563 | +0.001 | pipeline/scorecards.py |
| core | points | 30.0 | UH | n_flags | 5362 | 5443 | +81.000 | pipeline/scorecards.py |
| core | points | 30.0 | UNEP | n_flags | 5604 | 5605 | +1.000 | pipeline/scorecards.py |
| core | points | 30.0 | UNEP∧OSU | P | 0.308 | 0.309 | +0.001 | pipeline/scorecards.py |
| core | points | 30.0 | UNEP∧OSU | n_flags | 3391 | 3389 | -2.000 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | 1-of-6 | F1 | 0.178 | 0.177 | -0.001 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | 1-of-6 | n_flags | 37316 | 37346 | +30.000 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | 2-of-6 | n_flags | 20742 | 20766 | +24.000 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | 3-of-6 | F1 | 0.363 | 0.362 | -0.001 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | 3-of-6 | n_flags | 9116 | 9140 | +24.000 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | 4-of-6 | F1 | 0.425 | 0.424 | -0.001 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | 4-of-6 | P | 0.382 | 0.381 | -0.001 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | 4-of-6 | R | 0.478 | 0.477 | -0.001 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | 4-of-6 | n_flags | 3114 | 3123 | +9.000 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | 5-of-6 | F1 | 0.346 | 0.343 | -0.003 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | 5-of-6 | P | 0.581 | 0.579 | -0.002 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | 5-of-6 | R | 0.247 | 0.244 | -0.003 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | 5-of-6 | n_flags | 912 | 915 | +3.000 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | 6-of-6 | F1 | 0.171 | 0.172 | +0.001 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | 6-of-6 | P | 0.883 | 0.882 | -0.001 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | 6-of-6 | n_flags | 213 | 211 | -2.000 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | MS | n_flags | 7872 | 7878 | +6.000 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | UH | F1 | 0.229 | 0.228 | -0.001 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | UH | P | 0.171 | 0.169 | -0.002 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | UH | R | 0.348 | 0.349 | +0.001 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | UH | n_flags | 5362 | 5443 | +81.000 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | UNEP | F1 | 0.244 | 0.243 | -0.001 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | UNEP | P | 0.179 | 0.178 | -0.001 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | UNEP | R | 0.384 | 0.382 | -0.002 | pipeline/scorecards.py |
| core | points+possibly | 10.0 | UNEP | n_flags | 5604 | 5605 | +1.000 | pipeline/scorecards.py |
| field | field | 20.0 | UNEP debris (core region) | R_complete | 0.71 | 0.7 | -0.010 | pipeline/scorecards.py |
| strip-east | points | 10.0 | MS | n_flags | 3546 | 3545 | -1.000 | pipeline/scorecards.py |
| strip-east | points | 10.0 | UH | P | 0.12 | 0.118 | -0.002 | pipeline/scorecards.py |
| strip-east | points | 10.0 | UH | flag_share | 0.113 | 0.115 | +0.002 | pipeline/scorecards.py |
| strip-east | points | 10.0 | UH | n_flags | 4887 | 4968 | +81.000 | pipeline/scorecards.py |
| strip-west | points | 10.0 | MS | P | 0.051 | 0.052 | +0.001 | pipeline/scorecards.py |
| strip-west | points | 10.0 | MS | n_flags | 4398 | 4405 | +7.000 | pipeline/scorecards.py |

## expectations

| expectation | result | detail |
|---|---|---|
| IMPACT/OSU/LIST core P unchanged (id-mapped products untouched) | PASS | 3 rows |
| IMPACT/OSU/LIST core R unchanged (id-mapped products untouched) | PASS | 3 rows |
| IMPACT/OSU/LIST core n_flags unchanged (id-mapped products untouched) | PASS | 3 rows |
| Microsoft core flags move by <= 25 (largest-overlap -> IoU) | PASS | 7872 -> 7878 |
| UH core flags move by <= 2% (rule 3 snaps ~1,000 footprints gold's containment rule dropped) | PASS | 5362 -> 5443 |
| UNEP core flags move by <= 4% | PASS | 5604 -> 5605 |
| MS/UH/UNEP core precision moves by <= 0.01 | PASS | max |Δ| 0.002 |
| area-ranking correlations move by <= 0.02 | PASS | max |Δ| 0.012 |
| reference-point facts unchanged | PASS | 0 rows |

## added

- Caraballeda / facts / nan / CEMS / n_points_2_3 = 1468
- Caraballeda / facts / nan / CEMS / share_of_points_2_3 = 0.955729
- Caracas / facts / nan / CEMS / n_points_2_3 = 3
- Caracas / facts / nan / CEMS / share_of_points_2_3 = 0.00195312
- Moron / facts / nan / CEMS / n_points_2_3 = 26
- Moron / facts / nan / CEMS / share_of_points_2_3 = 0.0169271
- San Felipe / facts / nan / CEMS / n_points_2_3 = 14
- San Felipe / facts / nan / CEMS / share_of_points_2_3 = 0.00911458
- Santa Cruz / facts / nan / CEMS / n_points_2_3 = 3
- Santa Cruz / facts / nan / CEMS / share_of_points_2_3 = 0.00195312
- all / facts / nan / CEMS / n_points_1 = 1583
- all / facts / nan / CEMS / n_points_2_3 = 1536
- all / facts / nan / CEMS / n_points_all_grades = 3119
- all / facts / nan / ChatMap / n_complete = 328
- all / facts / nan / ChatMap / n_minimal = 24
- all / facts / nan / ChatMap / n_points = 415
- all / facts / nan / ChatMap / n_significant = 63
- all / facts / nan / IMPACT / aoi_km2 = 32712.7
- all / facts / nan / LIST / aoi_km2 = 223708
- all / facts / nan / MS / aoi_km2 = 210.241
- all / facts / nan / MS / base_buildings = 8339
- all / facts / nan / MS / collapsed = 71
- all / facts / nan / MS / delivered_footprints = 8410
- all / facts / nan / MS / mapped_by_iou = 8410
- all / facts / nan / MS / mapped_by_snap = 0
- all / facts / nan / MS / median_iou = 0.667
- all / facts / nan / MS / n_footprints = 72162
- all / facts / nan / MS / orphans = 0
- all / facts / nan / MS / share_mostly_obscured = 0.0360578
- all / facts / nan / OSU / added_v0_to_v1 = 42723
- all / facts / nan / OSU / aoi_km2 = 41463.2
- all / facts / nan / OSU / coverage_growth = 0.179395
- all / facts / nan / OSU / dropped_v0_to_v1 = 30565
- all / facts / nan / OSU / v0_flags_delivered = 58870
- all / facts / nan / OSU / v0_flags_on_base = 57066
- all / facts / nan / OSU / v0_share_probability_1 = 0.512111
- all / facts / nan / OSU / v1_flags_delivered = 69431
- all / facts / nan / OSU / v1_flags_on_base = 69224
- all / facts / nan / UH / aoi_km2 = 533.25
- all / facts / nan / UH / base_buildings = 75294
- all / facts / nan / UH / collapsed = 1066
- all / facts / nan / UH / delivered_footprints = 76378
- all / facts / nan / UH / mapped_by_iou = 75329
- all / facts / nan / UH / mapped_by_snap = 1031
- all / facts / nan / UH / median_iou = 0.99
- all / facts / nan / UH / orphans = 18
- all / facts / nan / UNEP / base_buildings = 75814
- all / facts / nan / UNEP / collapsed = 20073
- all / facts / nan / UNEP / delivered_footprints = 96046
- all / facts / nan / UNEP / mapped_by_iou = 92820
- all / facts / nan / UNEP / mapped_by_snap = 3067
- all / facts / nan / UNEP / median_iou = 0.413
- all / facts / nan / UNEP / orphans = 159
- all / facts / nan / h3-res11 / avg_area_km2 = 0.00214964
- all / facts / nan / h3-res12 / avg_area_km2 = 0.000307092
- all / facts / nan / h3-res7 / avg_area_km2 = 5.16129
- all / facts / nan / h3-res8 / avg_area_km2 = 0.737328
- all / facts / nan / h3-res9 / avg_area_km2 = 0.105333
- all / facts / nan / region / cems_extent_km2 = 505.468
- all / facts / nan / region / n_buildings_base = 702036
- all / facts / nan / region / products_overlap_km2 = 99.9962
- core / facts / nan / CEMS / n_damaged = 784
- core / facts / nan / CEMS / n_destroyed = 683
- core / facts / nan / CEMS / n_points_2_3 = 1467
- core / facts / nan / CEMS / n_possibly = 1319
- core / facts / nan / DISHA / cems_in_core = 1467
- core / facts / nan / DISHA / cems_in_extent = 886
- core / facts / nan / DISHA / covers_km2 = 29.2932
- core / facts / nan / DISHA / extent_km2 = 133.596
- core / facts / nan / DISHA / share_of_core = 0.481518
- core / facts / nan / MS / n_footprints = 61191
- core / facts / nan / MS / share_mostly_obscured = 0.0142831
- core / facts / nan / region / area_km2 = 60.835
- core / facts / nan / region / n_buildings = 57241
- core / facts / nan / spacing / median_nn_m = 9.61313
- core / facts / nan / spacing / share_nn_within_10m = 0.538443
- core / facts / nan / spacing / share_nn_within_20m = 0.932461
- core / labels-destroyed / 10.0 / IMPACT / F1 = 0.102
- core / labels-destroyed / 10.0 / IMPACT / P = 0.055
- core / labels-destroyed / 10.0 / IMPACT / R = 0.624
- core / labels-destroyed / 10.0 / IMPACT / n_flags = 10787
- core / labels-destroyed / 10.0 / IMPACT / n_pos = 957
- core / labels-destroyed / 10.0 / LIST / F1 = 0.079
- core / labels-destroyed / 10.0 / LIST / P = 0.042
- core / labels-destroyed / 10.0 / LIST / R = 0.7
- core / labels-destroyed / 10.0 / LIST / n_flags = 15906
- core / labels-destroyed / 10.0 / LIST / n_pos = 957
- core / labels-destroyed / 10.0 / MS / F1 = 0.143
- core / labels-destroyed / 10.0 / MS / P = 0.08
- core / labels-destroyed / 10.0 / MS / R = 0.659
- core / labels-destroyed / 10.0 / MS / n_flags = 7878
- core / labels-destroyed / 10.0 / MS / n_pos = 957
- core / labels-destroyed / 10.0 / OSU / F1 = 0.063
- core / labels-destroyed / 10.0 / OSU / P = 0.033
- core / labels-destroyed / 10.0 / OSU / R = 0.886
- core / labels-destroyed / 10.0 / OSU / n_flags = 25882
- core / labels-destroyed / 10.0 / OSU / n_pos = 957
- core / labels-destroyed / 10.0 / UH / F1 = 0.144
- core / labels-destroyed / 10.0 / UH / P = 0.085
- core / labels-destroyed / 10.0 / UH / R = 0.482
- core / labels-destroyed / 10.0 / UH / n_flags = 5443
- core / labels-destroyed / 10.0 / UH / n_pos = 957
- core / labels-destroyed / 10.0 / UNEP / F1 = 0.137
- core / labels-destroyed / 10.0 / UNEP / P = 0.08
- core / labels-destroyed / 10.0 / UNEP / R = 0.469
- core / labels-destroyed / 10.0 / UNEP / n_flags = 5605
- core / labels-destroyed / 10.0 / UNEP / n_pos = 957
- core / labels-destroyed / 10.0 / flat k-of-6 voting / F1 = 0.281
- core / labels-destroyed / 10.0 / flat k-of-6 voting / P = 0.184
- core / labels-destroyed / 10.0 / flat k-of-6 voting / R = 0.6
- core / labels-destroyed / 10.0 / flat k-of-6 voting / n_flags = 3123
- core / labels-destroyed / 10.0 / flat k-of-6 voting / n_pos = 957
- core / labels-destroyed / 10.0 / geography null (logistic) / F1 = 0.093
- core / labels-destroyed / 10.0 / geography null (logistic) / P = 0.05
- core / labels-destroyed / 10.0 / geography null (logistic) / R = 0.675
- core / labels-destroyed / 10.0 / geography null (logistic) / n_flags = 12864
- core / labels-destroyed / 10.0 / geography null (logistic) / n_pos = 957
- core / labels-destroyed / 10.0 / geography null (rand. forest) / F1 = 0.072
- core / labels-destroyed / 10.0 / geography null (rand. forest) / P = 0.039
- core / labels-destroyed / 10.0 / geography null (rand. forest) / R = 0.531
- core / labels-destroyed / 10.0 / geography null (rand. forest) / n_flags = 13112
- core / labels-destroyed / 10.0 / geography null (rand. forest) / n_pos = 957
- core / labels-destroyed / 10.0 / weighted fusion / F1 = 0.358
- core / labels-destroyed / 10.0 / weighted fusion / P = 0.262
- core / labels-destroyed / 10.0 / weighted fusion / R = 0.567
- core / labels-destroyed / 10.0 / weighted fusion / n_flags = 2075
- core / labels-destroyed / 10.0 / weighted fusion / n_pos = 957
- core / labels-dmg+destroyed / 10.0 / IMPACT / F1 = 0.174
- core / labels-dmg+destroyed / 10.0 / IMPACT / P = 0.104
- core / labels-dmg+destroyed / 10.0 / IMPACT / R = 0.542
- core / labels-dmg+destroyed / 10.0 / IMPACT / n_flags = 10787
- core / labels-dmg+destroyed / 10.0 / IMPACT / n_pos = 2064
- core / labels-dmg+destroyed / 10.0 / LIST / F1 = 0.151
- core / labels-dmg+destroyed / 10.0 / LIST / P = 0.086
- core / labels-dmg+destroyed / 10.0 / LIST / R = 0.659
- core / labels-dmg+destroyed / 10.0 / LIST / n_flags = 15906
- core / labels-dmg+destroyed / 10.0 / LIST / n_pos = 2064
- core / labels-dmg+destroyed / 10.0 / MS / F1 = 0.193
- core / labels-dmg+destroyed / 10.0 / MS / P = 0.122
- core / labels-dmg+destroyed / 10.0 / MS / R = 0.465
- core / labels-dmg+destroyed / 10.0 / MS / n_flags = 7878
- core / labels-dmg+destroyed / 10.0 / MS / n_pos = 2064
- core / labels-dmg+destroyed / 10.0 / OSU / F1 = 0.126
- core / labels-dmg+destroyed / 10.0 / OSU / P = 0.068
- core / labels-dmg+destroyed / 10.0 / OSU / R = 0.851
- core / labels-dmg+destroyed / 10.0 / OSU / n_flags = 25882
- core / labels-dmg+destroyed / 10.0 / OSU / n_pos = 2064
- core / labels-dmg+destroyed / 10.0 / UH / F1 = 0.18
- core / labels-dmg+destroyed / 10.0 / UH / P = 0.124
- core / labels-dmg+destroyed / 10.0 / UH / R = 0.327
- core / labels-dmg+destroyed / 10.0 / UH / n_flags = 5443
- core / labels-dmg+destroyed / 10.0 / UH / n_pos = 2064
- core / labels-dmg+destroyed / 10.0 / UNEP / F1 = 0.171
- core / labels-dmg+destroyed / 10.0 / UNEP / P = 0.117
- core / labels-dmg+destroyed / 10.0 / UNEP / R = 0.317
- core / labels-dmg+destroyed / 10.0 / UNEP / n_flags = 5605
- core / labels-dmg+destroyed / 10.0 / UNEP / n_pos = 2064
- core / labels-dmg+destroyed / 10.0 / flat k-of-6 voting / F1 = 0.323
- core / labels-dmg+destroyed / 10.0 / flat k-of-6 voting / P = 0.268
- core / labels-dmg+destroyed / 10.0 / flat k-of-6 voting / R = 0.406
- core / labels-dmg+destroyed / 10.0 / flat k-of-6 voting / n_flags = 3123
- core / labels-dmg+destroyed / 10.0 / flat k-of-6 voting / n_pos = 2064
- core / labels-dmg+destroyed / 10.0 / geography null (logistic) / F1 = 0.172
- core / labels-dmg+destroyed / 10.0 / geography null (logistic) / P = 0.1
- core / labels-dmg+destroyed / 10.0 / geography null (logistic) / R = 0.622
- core / labels-dmg+destroyed / 10.0 / geography null (logistic) / n_flags = 12864
- core / labels-dmg+destroyed / 10.0 / geography null (logistic) / n_pos = 2064
- core / labels-dmg+destroyed / 10.0 / geography null (rand. forest) / F1 = 0.142
- core / labels-dmg+destroyed / 10.0 / geography null (rand. forest) / P = 0.082
- core / labels-dmg+destroyed / 10.0 / geography null (rand. forest) / R = 0.523
- core / labels-dmg+destroyed / 10.0 / geography null (rand. forest) / n_flags = 13112
- core / labels-dmg+destroyed / 10.0 / geography null (rand. forest) / n_pos = 2064
- core / labels-dmg+destroyed / 10.0 / weighted fusion / F1 = 0.371
- core / labels-dmg+destroyed / 10.0 / weighted fusion / P = 0.37
- core / labels-dmg+destroyed / 10.0 / weighted fusion / R = 0.372
- core / labels-dmg+destroyed / 10.0 / weighted fusion / n_flags = 2075
- core / labels-dmg+destroyed / 10.0 / weighted fusion / n_pos = 2064
- core / labels-incl_possibly / 10.0 / IMPACT / F1 = 0.253
- core / labels-incl_possibly / 10.0 / IMPACT / P = 0.173
- core / labels-incl_possibly / 10.0 / IMPACT / R = 0.471
- core / labels-incl_possibly / 10.0 / IMPACT / n_flags = 10787
- core / labels-incl_possibly / 10.0 / IMPACT / n_pos = 3960
- core / labels-incl_possibly / 10.0 / LIST / F1 = 0.244
- core / labels-incl_possibly / 10.0 / LIST / P = 0.152
- core / labels-incl_possibly / 10.0 / LIST / R = 0.611
- core / labels-incl_possibly / 10.0 / LIST / n_flags = 15906
- core / labels-incl_possibly / 10.0 / LIST / n_pos = 3960
- core / labels-incl_possibly / 10.0 / MS / F1 = 0.249
- core / labels-incl_possibly / 10.0 / MS / P = 0.187
- core / labels-incl_possibly / 10.0 / MS / R = 0.373
- core / labels-incl_possibly / 10.0 / MS / n_flags = 7878
- core / labels-incl_possibly / 10.0 / MS / n_pos = 3960
- core / labels-incl_possibly / 10.0 / OSU / F1 = 0.214
- core / labels-incl_possibly / 10.0 / OSU / P = 0.123
- core / labels-incl_possibly / 10.0 / OSU / R = 0.806
- core / labels-incl_possibly / 10.0 / OSU / n_flags = 25882
- core / labels-incl_possibly / 10.0 / OSU / n_pos = 3960
- core / labels-incl_possibly / 10.0 / UH / F1 = 0.196
- core / labels-incl_possibly / 10.0 / UH / P = 0.169
- core / labels-incl_possibly / 10.0 / UH / R = 0.232
- core / labels-incl_possibly / 10.0 / UH / n_flags = 5443
- core / labels-incl_possibly / 10.0 / UH / n_pos = 3960
- core / labels-incl_possibly / 10.0 / UNEP / F1 = 0.209
- core / labels-incl_possibly / 10.0 / UNEP / P = 0.178
- core / labels-incl_possibly / 10.0 / UNEP / R = 0.252
- core / labels-incl_possibly / 10.0 / UNEP / n_flags = 5605
- core / labels-incl_possibly / 10.0 / UNEP / n_pos = 3960
- core / labels-incl_possibly / 10.0 / flat k-of-6 voting / F1 = 0.336
- core / labels-incl_possibly / 10.0 / flat k-of-6 voting / P = 0.381
- core / labels-incl_possibly / 10.0 / flat k-of-6 voting / R = 0.301
- core / labels-incl_possibly / 10.0 / flat k-of-6 voting / n_flags = 3123
- core / labels-incl_possibly / 10.0 / flat k-of-6 voting / n_pos = 3960
- core / labels-incl_possibly / 10.0 / geography null (logistic) / F1 = 0.26
- core / labels-incl_possibly / 10.0 / geography null (logistic) / P = 0.17
- core / labels-incl_possibly / 10.0 / geography null (logistic) / R = 0.553
- core / labels-incl_possibly / 10.0 / geography null (logistic) / n_flags = 12864
- core / labels-incl_possibly / 10.0 / geography null (logistic) / n_pos = 3960
- core / labels-incl_possibly / 10.0 / geography null (rand. forest) / F1 = 0.224
- core / labels-incl_possibly / 10.0 / geography null (rand. forest) / P = 0.146
- core / labels-incl_possibly / 10.0 / geography null (rand. forest) / R = 0.484
- core / labels-incl_possibly / 10.0 / geography null (rand. forest) / n_flags = 13112
- core / labels-incl_possibly / 10.0 / geography null (rand. forest) / n_pos = 3960
- core / labels-incl_possibly / 10.0 / weighted fusion / F1 = 0.347
- core / labels-incl_possibly / 10.0 / weighted fusion / P = 0.504
- core / labels-incl_possibly / 10.0 / weighted fusion / R = 0.264
- core / labels-incl_possibly / 10.0 / weighted fusion / n_flags = 2075
- core / labels-incl_possibly / 10.0 / weighted fusion / n_pos = 3960

## removed

- core / cells-agreement / 8.0 / weighted fusion / cells = 133
- core / cells-agreement / 8.0 / weighted fusion / cells_frac = 112
- core / cells-agreement / 8.0 / weighted fusion / rho = 0.711
- core / cells-agreement / 8.0 / weighted fusion / rho_frac = 0.647
- core / cells-agreement / 8.0 / weighted fusion / top20 = 0.5
- core / cells-agreement / 8.0 / weighted fusion / top20_exp = 0.5
- core / cells-agreement / 9.0 / weighted fusion / cells = 594
- core / cells-agreement / 9.0 / weighted fusion / cells_frac = 426
- core / cells-agreement / 9.0 / weighted fusion / rho = 0.566
- core / cells-agreement / 9.0 / weighted fusion / rho_frac = 0.577
- core / cells-agreement / 9.0 / weighted fusion / top20 = 0.25
- core / cells-agreement / 9.0 / weighted fusion / top20_exp = 0.25
