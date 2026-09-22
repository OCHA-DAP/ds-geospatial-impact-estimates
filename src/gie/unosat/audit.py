"""Silver/gold invariants (spec §5, S/G-rules) plus the bronze B-rules.

Each check returns ``(ok: bool, detail: str)``. `run_bronze_checks`,
`run_silver_checks` and `run_gold_checks` each print one PASS/FAIL line per
rule and return whether every rule in that section passed.
"""

from __future__ import annotations

import pandas as pd

from gie.unosat import common, gold, silver
from gie.unosat.store import BlobStore


def check_b1_no_pending(ledger: pd.DataFrame) -> tuple[bool, str]:
    n = int((ledger["status"] == "pending").sum())
    return n == 0, f"{n} pending"


def check_b2_census(ledger: pd.DataFrame, store: BlobStore) -> tuple[bool, str]:
    """Every uploaded row's (sha256, basename) exists with the recorded size,
    and every object under bronze/blob= is claimed by some uploaded row."""
    up = ledger[ledger["status"].isin(common.UPLOADED_STATUSES)]
    expected = {
        common.blob_path(r.sha256, r.resource_name): int(r.size_bytes) for r in up.itertuples()
    }
    got = store.list_sizes(common.BLOB_LISTING_PREFIX)
    missing = sorted(set(expected) - set(got))
    extra = sorted(set(got) - set(expected))
    wrong = sorted(p for p in set(expected) & set(got) if expected[p] != got[p])
    ok = not (missing or extra or wrong)
    detail = (
        f"{len(got)} objects; missing={len(missing)} extra={len(extra)} "
        f"size-mismatch={len(wrong)}"
    )
    if not ok:
        detail += (
            f" | missing[:3]={missing[:3]} extra[:3]={extra[:3]} "
            f"size[:3]={wrong[:3]}"
        )
    return ok, detail


def check_b3_domains(
    ledger: pd.DataFrame, status_df: pd.DataFrame
) -> tuple[bool, str]:
    gdb = ledger[
        (ledger["format"] == "Geodatabase") & ledger["status"].isin(common.UPLOADED_STATUSES)
    ]
    want = set(gdb["sha256"].dropna())
    have = set(status_df["sha256"]) if len(status_df) else set()
    missing = sorted(want - have)
    return (
        not missing,
        f"{len(want)} GDBs; without domain status: {len(missing)} {missing[:3]}",
    )


def run_bronze_checks(
    ledger: pd.DataFrame, store: BlobStore, status_df: pd.DataFrame
) -> bool:
    ok = True
    for name, (passed, detail) in {
        "B1 no pending targets": check_b1_no_pending(ledger),
        "B2 blob census matches ledger (paths+sizes, both directions)": check_b2_census(
            ledger, store
        ),
        "B3 every uploaded GDB has a domains status": check_b3_domains(ledger, status_df),
    }.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}  {detail}")
        ok &= passed
    return ok


# ---------------------------------------------------------------------------
# Silver (S1-S7). Vocabularies are the exact strings from the global
# constraints doc; `class_method = "unresolved_code"` is kept in the set even
# though silver never emits it (a layer is always classifiable by the point
# `build_layer` reaches it) — S4 checks membership, not reachability.
# ---------------------------------------------------------------------------

VOCABULARIES: dict[str, frozenset[str]] = {
    "layer_kind": frozenset(
        {
            "water",
            "water_pre",
            "flood",
            "flood_possible",
            "other_water",
            "aggregate_max",
            "aggregate_min",
        }
    ),
    "role": frozenset({"footprint", "not_analysed"}),
    "class_method": frozenset(
        {"domain", "text", "decoded_column", "layer_name", "unresolved_code"}
    ),
    "acq_precision": frozenset({"date", "window", "none"}),
    "acq_method": frozenset({"attribute", "filename", "window", "none"}),
    "geometry_source": frozenset({"gdb", "shp"}),
    "status": frozenset(silver.STATUSES),
}

_EVENT_CODE_DATE = r"^[A-Z]{2}(\d{8})[A-Z]{3}"


def _has_mismatch_list(value: object) -> bool:
    """Whether a `shp_gdb_mismatch` cell holds a real (possibly empty) list,
    as opposed to `None`/NaN. A parquet round trip can hand back a numpy
    array rather than a `list`, so this checks shape, not type."""
    if value is None:
        return False
    return not (isinstance(value, float) and pd.isna(value))


def _s1_missing(
    ledger: pd.DataFrame, layers_df: pd.DataFrame, proc_df: pd.DataFrame
) -> tuple[set[tuple[str, str]], list[tuple[str, str]], dict[str, str]]:
    """``(every selected (sha256, layer), the missing ones, {sha256: code})``.

    "Selected" means the run's own selector chose it — not every inventoried
    layer: a layer present only in a dataset's SHP export when the GDB is the
    chosen geometry source is never read for that dataset and legitimately
    has no processing row.
    """
    units = silver.select_units(ledger, layers_df)
    have = set(zip(proc_df["sha256"], proc_df["layer"], strict=True)) if len(proc_df) else set()
    want: set[tuple[str, str]] = set()
    sha_code: dict[str, str] = {}
    for u in units:
        sha_code[u["sha256"]] = u["code"]
        inv = layers_df.loc[layers_df["sha256"] == u["sha256"], "layer"].drop_duplicates()
        want.update((u["sha256"], layer) for layer in inv)
    missing = sorted(want - have)
    return want, missing, sha_code


def check_s1_processing_covers_selected(
    ledger: pd.DataFrame, layers_df: pd.DataFrame, proc_df: pd.DataFrame
) -> tuple[bool, str]:
    want, missing, _ = _s1_missing(ledger, layers_df, proc_df)
    ok = not missing
    detail = f"{len(want)} selected (sha256, layer) units; {len(missing)} missing from processing"
    if missing:
        detail += f" (e.g. {missing[:3]})"
    return ok, detail


def _s2_missing_by_table(proc_df: pd.DataFrame, store: BlobStore) -> dict[str, list[str]]:
    problems: dict[str, list[str]] = {}
    for table in ("observed_event", "coverage"):
        need = set(
            proc_df.loc[(proc_df["table"] == table) & (proc_df["status"] == "ok"), "code"].dropna()
        )
        have = {
            p.split("code=", 1)[1].split("/", 1)[0]
            for p in store.list_sizes(f"{common.SILVER}/{table}/code=")
        }
        missing = sorted(need - have)
        if missing:
            problems[table] = missing
    return problems


def check_s2_partitions_written(proc_df: pd.DataFrame, store: BlobStore) -> tuple[bool, str]:
    """Every code with >=1 `ok` `observed_event` layer has an `observed_event`
    partition in blob, and likewise for `coverage`."""
    problems = _s2_missing_by_table(proc_df, store)
    ok = not problems
    detail = "; ".join(
        f"{table}: {len(codes)} codes missing a partition {codes[:3]}"
        for table, codes in problems.items()
    )
    return ok, (detail or "every code with an ok layer has its partition")


def _s3_bad(
    rows: pd.DataFrame, *, now: pd.Timestamp, min_year: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """``(dated rows, rows outside [min_year, now], rows off by > a year from
    their event code's date)``. Rows with `acq_precision == "none"` carry no
    date anywhere and are silver's own record of that — not this rule's
    concern (gold excludes them on the same basis)."""
    dated = rows[rows["acq_precision"] != "none"].copy()
    if dated.empty:
        return dated, dated, dated
    start = pd.to_datetime(dated["acq_window_start"]).fillna(pd.to_datetime(dated["acq_datetime"]))
    end = pd.to_datetime(dated["acq_window_end"]).fillna(pd.to_datetime(dated["acq_datetime"]))
    mid = start + (end - start) / 2
    out_of_range = dated[(mid.dt.year < min_year) | (mid.dt.year > now.year)]
    event_date = pd.to_datetime(
        dated["code"].astype(str).str.extract(_EVENT_CODE_DATE)[0],
        format="%Y%m%d",
        errors="coerce",
    )
    off_by_year = dated[event_date.notna() & ((mid - event_date).abs() > pd.Timedelta(days=366))]
    return dated, out_of_range, off_by_year


def check_s3_acquisition_dates(
    rows: pd.DataFrame, *, now: pd.Timestamp | None = None, min_year: int = 2005
) -> tuple[bool, str]:
    """Every dated acquisition falls in ``[min_year, now]`` and within one
    year of its event code's date (`FL20220424SSD` -> 2022-04-24). ``rows``
    is the concatenation of `observed_event` and `coverage` rows across
    whatever codes are being audited: `code`, `acq_datetime`,
    `acq_window_start`, `acq_window_end`, `acq_precision`."""
    now = now if now is not None else pd.Timestamp.now()
    if now.tzinfo is not None:
        now = now.tz_localize(None)
    dated, out_of_range, off_by_year = _s3_bad(rows, now=now, min_year=min_year)
    if dated.empty:
        return True, "no dated rows"
    bad = pd.concat([out_of_range, off_by_year]).drop_duplicates()
    ok = bad.empty
    detail = (
        f"{len(dated)} dated rows; {len(out_of_range)} outside [{min_year}, {now.year}], "
        f"{len(off_by_year)} more than a year from their event code's date"
    )
    if not ok:
        detail += f" | codes: {sorted(bad['code'].unique())[:5]}"
    return ok, detail


def check_s4_vocabularies(series_by_column: dict[str, pd.Series]) -> tuple[bool, str]:
    """Every value in each given column lies within its documented
    vocabulary. Membership only, not coverage: a vocabulary member that never
    appears (`class_method = "unresolved_code"`) is not a failure here."""
    violations: dict[str, list[str]] = {}
    for col, series in series_by_column.items():
        vocab = VOCABULARIES.get(col)
        if vocab is None:
            raise ValueError(f"no documented vocabulary for column {col!r}")
        bad = sorted(str(v) for v in set(series.dropna().unique()) - vocab)
        if bad:
            violations[col] = bad
    ok = not violations
    detail = "; ".join(f"{col}: {bad}" for col, bad in violations.items())
    return ok, (detail or f"{len(series_by_column)} columns within vocabulary")


def _s5_share(proc_df: pd.DataFrame) -> pd.Series:
    return proc_df.groupby("code")["status"].agg(lambda s: (s == "unclassified").sum() / len(s))


def check_s5_unclassified_share(
    proc_df: pd.DataFrame, *, threshold: float = 0.04
) -> tuple[bool, str]:
    if proc_df.empty:
        return True, "no processing rows"
    per_code = _s5_share(proc_df)
    bad = sorted(per_code[per_code > threshold].index)
    ok = not bad
    detail = f"{len(bad)} codes over {threshold:.0%} unclassified"
    if bad:
        worst = per_code.loc[bad].sort_values(ascending=False)
        detail += f": {[(c, round(v, 3)) for c, v in worst.items()][:5]}"
    return ok, detail


def _s6_bad(proc_df: pd.DataFrame) -> pd.DataFrame:
    has_list = proc_df["shp_gdb_mismatch"].map(_has_mismatch_list)
    should_have = proc_df["sibling_status"] == "ok"
    return proc_df[has_list != should_have]


def check_s6_sibling_consistency(proc_df: pd.DataFrame) -> tuple[bool, str]:
    """`shp_gdb_mismatch` is a list (possibly empty) exactly when
    `sibling_status == "ok"`; `None` otherwise — no shapefile sibling at all,
    or one that could not be inventoried (`sibling_status` says which).
    `None` is never itself a failure; the two columns disagreeing is."""
    if proc_df.empty:
        return True, "no processing rows"
    bad = _s6_bad(proc_df)
    ok = bad.empty
    detail = f"{len(bad)} rows where shp_gdb_mismatch/sibling_status disagree"
    if not ok:
        detail += f": {bad[['sha256', 'layer', 'sibling_status']].head(3).to_dict('records')}"
    return ok, detail


def check_s7_all_uploaded(proc_df: pd.DataFrame) -> tuple[bool, str]:
    """After a clean run, every layer file the ledger says it built is
    confirmed in blob — `silver.unuploaded` must be empty."""
    stale = silver.unuploaded(proc_df)
    n = len(stale)
    detail = f"{n} rows built but not confirmed uploaded"
    if n:
        detail += f": {list(zip(stale['sha256'].str[:8], stale['layer'], strict=True))[:3]}"
    return n == 0, detail


def silver_surfaces(proc_df: pd.DataFrame) -> dict[str, int]:
    """Counts to report alongside the S-rules — real properties of the
    archive, not failures: `format_mismatch` (HDX's `format` label disagreed
    with what the zip's layer inventory said it was) and a content listed
    under more than one event code (`codes_listed`)."""
    if proc_df.empty:
        return {"format_mismatch": 0, "multi_code_contents": 0}
    format_mismatch = int(proc_df["format_mismatch"].fillna(False).astype(bool).sum())
    multi_code = int(
        proc_df["codes_listed"]
        .map(lambda v: isinstance(v, (list, tuple)) and len(v) > 1)
        .sum()
    )
    return {"format_mismatch": format_mismatch, "multi_code_contents": multi_code}


def run_silver_checks(
    ledger: pd.DataFrame,
    layers_df: pd.DataFrame,
    proc_df: pd.DataFrame,
    store: BlobStore,
    acq_rows: pd.DataFrame,
    vocab_series: dict[str, pd.Series],
) -> bool:
    ok = True
    for name, (passed, detail) in {
        "S1 processing covers every selected (sha256, layer)": check_s1_processing_covers_selected(
            ledger, layers_df, proc_df
        ),
        "S2 every ok-layer code has its partition": check_s2_partitions_written(proc_df, store),
        "S3 acquisition dates plausible": check_s3_acquisition_dates(acq_rows),
        "S4 vocabularies within documented sets": check_s4_vocabularies(vocab_series),
        "S5 unclassified share per code <= 4%": check_s5_unclassified_share(proc_df),
        "S6 shp/gdb sibling check recorded consistently": check_s6_sibling_consistency(proc_df),
        "S7 every built layer confirmed uploaded": check_s7_all_uploaded(proc_df),
    }.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}  {detail}")
        ok &= passed
    surfaces = silver_surfaces(proc_df)
    print(
        f"  (report) format_mismatch={surfaces['format_mismatch']} "
        f"multi_code_contents={surfaces['multi_code_contents']}"
    )
    return ok


# ---------------------------------------------------------------------------
# Gold (G1-G2)
# ---------------------------------------------------------------------------


def _g1_bad(index: pd.DataFrame) -> pd.DataFrame:
    return index[(index["valid_basis"] != "none") & index["valid_area_km2"].isna()]


def check_g1_valid_mask_present(index: pd.DataFrame) -> tuple[bool, str]:
    """Every label set has `geom_valid`, or is explicit that it has none
    (`valid_basis == "none"`)."""
    if index.empty:
        return True, "no label sets"
    bad = _g1_bad(index)
    ok = bad.empty
    detail = f"{len(bad)} label sets claim a valid_basis but carry no geom_valid"
    if not ok:
        detail += f" | codes: {sorted(bad['code'].unique())[:5]}"
    return ok, detail


def _g2_bad(
    observed_by_code: dict[str, pd.DataFrame], index: pd.DataFrame
) -> list[tuple[str, int, int]]:
    bad = []
    for code, obs in observed_by_code.items():
        datable = obs[obs["acq_precision"] != "none"]
        silver_excluded = int(datable["layer_kind"].isin(gold.EXCLUDED_KINDS).sum())
        index_excluded = int(index.loc[index["code"] == code, "excluded_aggregate_n"].sum())
        if silver_excluded != index_excluded:
            bad.append((code, silver_excluded, index_excluded))
    return bad


def check_g2_excluded_accounting(
    observed_by_code: dict[str, pd.DataFrame], index: pd.DataFrame
) -> tuple[bool, str]:
    """No `aggregate_max`/`aggregate_min`/`other_water` polygon contributes to
    a gold geometry: for every code, `excluded_aggregate_n` summed over its
    label sets equals the count of such (datable) polygons in its silver
    `observed_event` partition."""
    bad = _g2_bad(observed_by_code, index)
    ok = not bad
    detail = f"{len(bad)} codes where excluded_aggregate_n disagrees with silver's count"
    if bad:
        detail += f": {bad[:5]}"
    return ok, detail


def run_gold_checks(index: pd.DataFrame, observed_by_code: dict[str, pd.DataFrame]) -> bool:
    ok = True
    for name, (passed, detail) in {
        "G1 every label set has geom_valid or valid_basis='none'": check_g1_valid_mask_present(
            index
        ),
        "G2 excluded-kind polygons fully accounted for": check_g2_excluded_accounting(
            observed_by_code, index
        ),
    }.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}  {detail}")
        ok &= passed
    return ok


def label_coverage_summary(index: pd.DataFrame) -> dict:
    """Report only, not a pass/fail rule: the shape of the label archive.
    `valid_basis == "none"` (no exact-interval footprint match) is expected to
    be common — a property of the archive, not a defect."""
    if index.empty:
        return {"n_label_sets": 0}
    by_sensor_precision = index.groupby(["sensor_class", "acq_precision"], dropna=False).size()
    countries = index["countries"].dropna().astype(str).str.split("; ").explode()
    return {
        "n_label_sets": int(len(index)),
        "by_valid_basis": index["valid_basis"].value_counts(dropna=False).to_dict(),
        "by_sensor_class_acq_precision": {
            f"{sensor}/{precision}": int(n)
            for (sensor, precision), n in by_sensor_precision.items()
        },
        "by_country": countries.value_counts().to_dict(),
    }


def stale_codes(
    ledger: pd.DataFrame,
    layers_df: pd.DataFrame,
    proc_df: pd.DataFrame,
    store: BlobStore,
    acq_rows: pd.DataFrame,
    index: pd.DataFrame,
    observed_by_code: dict[str, pd.DataFrame],
    *,
    unclassified_threshold: float = 0.04,
    now: pd.Timestamp | None = None,
    min_year: int = 2005,
) -> set[str]:
    """Every code touched by an S/G failure — the defect-fix loop's
    reprocessing list, written to `audit_stale_codes.txt`."""
    now = now if now is not None else pd.Timestamp.now()
    if now.tzinfo is not None:
        now = now.tz_localize(None)
    codes: set[str] = set()

    _, missing, sha_code = _s1_missing(ledger, layers_df, proc_df)
    codes.update(sha_code[sha] for sha, _ in missing if sha in sha_code)

    for table_missing in _s2_missing_by_table(proc_df, store).values():
        codes.update(table_missing)

    if not acq_rows.empty:
        _, out_of_range, off_by_year = _s3_bad(acq_rows, now=now, min_year=min_year)
        codes.update(pd.concat([out_of_range, off_by_year])["code"])

    if not proc_df.empty:
        per_code = _s5_share(proc_df)
        codes.update(per_code[per_code > unclassified_threshold].index)
        codes.update(_s6_bad(proc_df)["code"].dropna())
        codes.update(silver.unuploaded(proc_df)["code"].dropna())

    if not index.empty:
        codes.update(_g1_bad(index)["code"])

    codes.update(code for code, _, _ in _g2_bad(observed_by_code, index))
    return codes
