"""Render a human-readable status report of the CEMS flood archive, straight
from the ledger files — nothing hardcoded, safe to run at any point during or
after a harvest to see the true current state.

Reads {work_dir}/products.parquet (+ zip_contents.parquet, transfers.jsonl,
activations.parquet when present) and writes {work_dir}/status_report.html —
or, with --pages, pages/cems-flood-archive/index.html (with the site's
back-home crumb), which deploys via GitHub Pages on push to v1.

Run:  uv run --group etl --group api python pipelines/cems_flood/report.py [--pages]
"""

from __future__ import annotations

import argparse
import html
import json
from datetime import UTC, datetime
from pathlib import Path
from string import Template

import pandas as pd

STATUS_META = {
    # status -> (group for the bar, chip class, set by, meaning)
    "uploaded": (
        "uploaded",
        "uploaded",
        "harvest",
        "In blob, size-verified; sha256 + member inventory recorded",
    ),
    "pending": ("pending", "pending", "discovery", "Has a download URL; will be fetched"),
    "failed_download": (
        "failed",
        "failed",
        "harvest",
        "Download failed; HTTP status + error kept; retried via --retry-failed",
    ),
    "failed_upload": (
        "failed",
        "failed",
        "harvest",
        "Upload failed; error kept; retried via --retry-failed",
    ),
    "excluded_ref": (
        "excluded",
        "excluded",
        "discovery",
        "Pre-event Reference map — inventoried, deliberately not fetched",
    ),
    "unavailable_status_N": (
        "unavail",
        "unavail",
        "discovery",
        "New-portal product closed without delivery (never published)",
    ),
    "unavailable_not_migrated": (
        "unavail",
        "unavail",
        "discovery",
        "Legacy activation whose products were never migrated to the archive portal",
    ),
    "unavailable_no_products": ("unavail", "unavail", "discovery", "Activation delivered nothing"),
    "unavailable_no_url": (
        "unavail",
        "unavail",
        "discovery",
        "Product not (yet) delivered, not closed",
    ),
}
BAR_GROUPS = [  # order controls bar segments; palette validated for this adjacency
    ("uploaded", "uploaded", "seg-uploaded"),
    ("pending", "pending", "seg-pending"),
    ("failed", "failed", "seg-failed"),
    ("unavail", "unavailable (upstream)", "seg-unavail"),
    ("excluded", "excluded (REF maps)", "seg-excluded"),
]


def esc(v) -> str:
    return html.escape("" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))


def cell(v, cls="") -> str:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return '<td class="null">—</td>'
    return f'<td class="{cls}">{esc(v)}</td>'


def n(v) -> str:
    return f"{int(v):,}"


def sample_rows_html(led: pd.DataFrame) -> str:
    """One representative real row per interesting status."""
    picks: list[pd.Series] = []
    for mask in [
        (led.status == "uploaded") & led.sha256.notna(),
        led.status.str.startswith("failed"),
        (led.status == "pending") & (led.source == "archive"),
        (led.status == "pending") & (led.source == "new_portal"),
        led.status == "excluded_ref",
        led.status == "unavailable_not_migrated",
        led.status == "unavailable_status_N",
    ]:
        if mask.any():
            picks.append(led[mask].iloc[0])
    out = []
    for r in picks:
        chip = STATUS_META[r["status"]][1]
        tid = r["target_id"]
        tid_short = tid if len(tid) <= 46 else tid[:12] + "…" + tid[-30:]
        size = None if pd.isna(r["size_bytes"]) else f"{r['size_bytes'] / 1e6:.2f} MB"
        nm = None if pd.isna(r["n_members"]) else int(r["n_members"])
        sha = None if pd.isna(r["sha256"]) else r["sha256"][:8] + "…"
        dt = None if pd.isna(r["delivery_time"]) else str(r["delivery_time"])[:10]
        out.append(
            "<tr>"
            + f'<td class="mono" title="{esc(tid)}">{esc(tid_short)}</td>'
            + f'<td><span class="chip chip-{chip}">{esc(r["status"])}</span></td>'
            + cell(r["product_class"])
            + cell(r["source"])
            + cell(r["aoi"], "wrap")
            + cell(dt, "mono")
            + cell(size, "num")
            + cell(nm, "num")
            + (
                f'<td class="mono" title="{esc(r["sha256"])}">{esc(sha)}</td>'
                if sha
                else '<td class="null">—</td>'
            )
            + cell(r["error"], "mono")
            + "</tr>"
        )
    return "\n".join(out)


CRUMB = '<p class="crumb"><a href="../">← Geospatial Impact Estimates</a></p>'

DROP_REASONS = {
    # per-code explanation when an activation never reaches the label corpus
    "excluded_ref": "only pre-event Reference maps were produced — no delineation to harvest",
    "unavailable_not_migrated": "products never migrated to the archive portal",
    "unavailable_status_N": "activation closed without delivering products",
    "unavailable_no_products": "activation delivered nothing",
    "unavailable_no_url": "products not (yet) delivered",
    "failed_download": "download fails permanently upstream",
}


def funnel_html(work: Path, led: pd.DataFrame, n_act: int) -> str:
    """Activations -> archived -> labelled, with every drop-out accounted for.

    Only renders once gold exists (label_index.parquet in the work dir);
    before that the harvest sections above tell the whole story.
    """
    idx_path = work / "label_index.parquet"
    if not idx_path.exists() or not n_act:
        return ""
    idx = pd.read_parquet(idx_path)
    uploaded = set(led.loc[led.status == "uploaded", "code"])
    labelled = set(idx.code)

    drop_rows = []
    for code, sub in led.groupby("code"):
        if code in labelled:
            continue
        if code in uploaded:
            why = (
                "zips archived, but no product contains a flood extent layer "
                "(flood receded / hydrography-only delineation)"
            )
        else:
            why = DROP_REASONS.get(sub.status.mode()[0], sub.status.mode()[0])
        drop_rows.append(
            f'<tr><td class="mono">{esc(code)}</td><td class="wrap">{esc(why)}</td></tr>'
        )

    return f"""
<section>
<h2>From activations to labels</h2>
<p>Every EMSR flood activation either contributes label sets or is listed below with
the reason it can't. Nothing is silently dropped.</p>
<div class="stats">
  <div class="stat"><div class="n">{n(n_act)}</div>
    <div class="l">flood activations found</div></div>
  <div class="stat"><div class="n">{n(len(uploaded))}</div>
    <div class="l">with zips archived</div></div>
  <div class="stat"><div class="n">{n(len(labelled))}</div>
    <div class="l">with flood labels</div></div>
  <div class="stat"><div class="n">{n(len(idx))}</div>
    <div class="l">label sets in gold</div></div>
</div>
<div class="tblwrap"><table>
<thead><tr><th>code</th><th>why it has no labels ({n(len(drop_rows))} activations)</th></tr></thead>
<tbody>{"".join(drop_rows)}</tbody>
</table></div>
</section>
"""


def build(work: Path, dest: Path | None = None, crumb: bool = False) -> Path:
    led = pd.read_parquet(work / "products.parquet")
    counts = led.status.value_counts().to_dict()
    unknown = set(counts) - set(STATUS_META)
    if unknown:  # a new status must be described, not silently lumped in
        raise ValueError(f"statuses missing from STATUS_META: {unknown}")

    group_n = {g: 0 for g, _, _ in BAR_GROUPS}
    for status, cnt in counts.items():
        group_n[STATUS_META[status][0]] += cnt
    segments = [
        {"label": label, "n": group_n[g], "cls": cls} for g, label, cls in BAR_GROUPS if group_n[g]
    ]

    fetchable = led.status.isin(["pending", "uploaded", "failed_download", "failed_upload"])
    n_uploaded = int((led.status == "uploaded").sum())
    up = led[led.status == "uploaded"]
    gb = up.size_bytes.sum() / 1e9 if n_uploaded else 0.0
    pend_cls = led[led.status == "pending"].product_class.value_counts().to_dict()

    status_table = "\n".join(
        "<tr>"
        f'<td><span class="chip chip-{STATUS_META[s][1]}">{esc(s)}</span></td>'
        f'<td>{STATUS_META[s][2]}</td><td class="wrap">{esc(STATUS_META[s][3])}</td>'
        f'<td class="num">{n(c)}</td></tr>'
        for s, c in sorted(counts.items(), key=lambda kv: -kv[1])
    )

    # newest fully-recorded upload, expanded
    kv_html = ""
    zc_html = ""
    if n_uploaded and up.sha256.notna().any():
        r = up[up.sha256.notna()].sort_values("uploaded_at").iloc[-1]
        kv_html = "".join(
            f'<dt>{esc(k)}</dt><dd class="mono">{esc(r[k])}</dd>'
            for k in [
                "target_id",
                "code",
                "source",
                "aoi",
                "title",
                "product_class",
                "delivery_time",
                "url",
                "blob_path",
                "status",
                "attempts",
                "attempted_at",
                "uploaded_at",
                "sha256",
                "size_bytes",
                "n_members",
            ]
        )
        zc_path = work / "zip_contents.parquet"
        if zc_path.exists():
            zc = pd.read_parquet(zc_path)
            mine = zc[zc.target_id == r["target_id"]].nlargest(8, "file_size")
            zc_html = "\n".join(
                f'<tr><td class="mono">{esc(m.member)}</td>'
                f'<td class="num">{n(m.file_size)}</td>'
                f'<td class="num">{n(m.compress_size)}</td></tr>'
                for m in mine.itertuples()
            )
            n_mine = (zc.target_id == r["target_id"]).sum()
            zc_html += (
                f'<tr><td class="muted" colspan="3">… of {n(n_mine)} members in this zip; '
                f"{n(len(zc))} member rows across "
                f"{n(zc.target_id.nunique())} inventoried zips</td></tr>"
            )

    tr_html = ""
    tr_path = work / "transfers.jsonl"
    if tr_path.exists():
        lines = tr_path.read_text().strip().splitlines()
        tr_html = esc(json.dumps(json.loads(lines[-1]), indent=2))
        tr_note = f"{n(len(lines))} attempt records so far"
    else:
        tr_note = "no attempts yet"

    act_html = ""
    act_path = work / "activations.parquet"
    n_act = 0
    if act_path.exists():
        act = pd.read_parquet(act_path).sort_values("num", ascending=False)
        n_act = len(act)
        act_html = "\n".join(
            "<tr>"
            + cell(a.code, "mono")
            + cell(a.name)
            + cell(a.countries)
            + cell(str(a.activationTime)[:10], "mono")
            + cell(int(a.n_aois), "num")
            + cell(int(a.n_products), "num")
            + cell("yes" if a.closed else "no")
            + "</tr>"
            for a in act.head(3).itertuples()
        )

    failed_n = int(led.status.str.startswith("failed").sum())
    tpl = Template((Path(__file__).parent / "report_template.html").read_text())
    out = tpl.substitute(
        funnel_section=funnel_html(work, led, n_act),
        generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        n_activations=n(n_act),
        n_rows=n(len(led)),
        n_fetchable=n(int(fetchable.sum())),
        n_uploaded=n(n_uploaded),
        n_failed=n(failed_n),
        gb=f"{gb:.1f}",
        pct=f"{100 * n_uploaded / max(int(fetchable.sum()), 1):.1f}",
        pending_classes=" · ".join(f"{k} {n(v)}" for k, v in pend_cls.items()),
        segments_json=json.dumps(segments),
        status_table=status_table,
        sample_rows=sample_rows_html(led),
        kv=kv_html or "<dt>—</dt><dd>no fully-recorded uploads yet</dd>",
        zip_rows=zc_html or '<tr><td class="muted" colspan="3">no inventoried zips yet</td></tr>',
        transfer_json=tr_html or "// no attempts yet",
        transfer_note=tr_note,
        activation_rows=act_html,
        crumb=CRUMB if crumb else "",
    )
    if crumb:
        # pages is served raw (an artifact publish injects the shell itself):
        # wrap in a full document, template head content up to </style>
        cut = out.index("</style>") + len("</style>")
        out = (
            '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"{out[:cut]}\n</head>\n<body>\n{out[cut:]}\n</body>\n</html>\n"
        )
    dest = dest or work / "status_report.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(out)
    print(f"report -> {dest}")
    return dest


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", default="/tmp/gie_cems_flood_archive", type=Path)
    ap.add_argument(
        "--pages",
        action="store_true",
        help="write to pages/cems-flood-archive/index.html (deploys on push to v1)",
    )
    args = ap.parse_args(argv)
    dest = None
    if args.pages:
        dest = Path(__file__).parents[2] / "pages" / "cems-flood-archive" / "index.html"
    build(args.work_dir, dest=dest, crumb=args.pages)


if __name__ == "__main__":
    main()
