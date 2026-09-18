"""Build the harvest ledger from the HDX catalogue (spec §1).

One ledger row per RESOURCE VERSION (``{resource_id}@{last_modified}``): a
resource re-published upstream becomes a new row; the old row is kept and
flagged ``missing_upstream`` when it no longer appears. Re-running is the
backfill mechanism: fresh discovery merges onto the existing ledger and
transfer outcomes survive (same model as cems_flood/discovery.py).
"""

from __future__ import annotations

import pandas as pd

from gie.unosat import common

_TRANSFER_COLS = [
    "status", "http_status", "error", "attempts", "attempted_at",
    "uploaded_at", "sha256", "size_bytes", "n_members",
]
_TRANSFER_STATUSES = common.UPLOADED_STATUSES | common.RETRYABLE_STATUSES | common.TERMINAL_STATUSES


def fetch_unosat_datasets(user_agent: str = common.USER_AGENT) -> list[dict]:
    """Every dataset of HDX organisation ``unosat`` with its resources, as plain
    dicts. Live call; not unit-tested (the pure functions below are)."""
    from hdx.api.configuration import Configuration
    from hdx.data.dataset import Dataset

    try:
        Configuration.create(hdx_site="prod", user_agent=user_agent, hdx_read_only=True)
    except Exception as e:  # already configured in this process
        if "already" not in str(e).lower():
            raise
    datasets = Dataset.search_in_hdx(fq="organization:unosat", page_size=1000)
    out: list[dict] = []
    for ds in datasets:
        d = dict(ds)
        d["resources"] = [dict(r) for r in ds.get_resources()]
        out.append(d)
    if not out:
        raise RuntimeError("HDX returned zero UNOSAT datasets — catalogue or auth problem")
    return out


def datasets_table(datasets: list[dict]) -> pd.DataFrame:
    rows = []
    for d in datasets:
        rows.append(
            {
                "dataset_id": d["id"],
                "dataset_name": d["name"],
                "title": d.get("title"),
                "dataset_date": d.get("dataset_date"),
                "countries": "; ".join(
                    g.get("title") or g.get("name") for g in d.get("groups") or []
                ),
                "tags": "; ".join(t["name"] for t in d.get("tags") or []),
                "licence": d.get("license_id"),
                "notes": d.get("notes"),
                "methodology": d.get("methodology_other") or d.get("methodology"),
                "metadata_created": d.get("metadata_created"),
                "metadata_modified": d.get("metadata_modified"),
                "n_resources": len(d.get("resources") or []),
            }
        )
    return pd.DataFrame(rows)


def resources_ledger(datasets: list[dict]) -> pd.DataFrame:
    rows = []
    for d in datasets:
        for r in d.get("resources") or []:
            code = common.parse_event_code(r.get("name") or "") or {}
            fmt = r.get("format")
            rows.append(
                {
                    "target_id": f"{r['id']}@{r.get('last_modified')}",
                    "dataset_id": d["id"],
                    "dataset_name": d["name"],
                    "resource_id": r["id"],
                    "resource_name": r.get("name"),
                    "format": fmt,
                    "url": r.get("url"),
                    "host": common.host_of(r.get("url") or ""),
                    "hdx_size": r.get("size"),
                    "hdx_hash": r.get("hash") or None,
                    "last_modified": r.get("last_modified"),
                    "event_code": code.get("event_code"),
                    "hazard_prefix": code.get("hazard_prefix"),
                    "iso3": code.get("iso3"),
                    "scope": common.scope_for(code.get("hazard_prefix")),
                    "licence": d.get("license_id"),
                    "status": "pending" if fmt in common.HARVEST_FORMATS else "excluded_kmz",
                    "attempts": 0,
                    "missing_upstream": False,
                }
            )
    led = pd.DataFrame(rows).reindex(columns=common.LEDGER_COLS)
    dup = led[led["target_id"].duplicated(keep=False)]
    if len(dup):
        raise RuntimeError(f"duplicate target_id in HDX listing (same resource twice?):\n{dup}")
    return common.coerce_ledger_dtypes(led)


def merge_ledgers(fresh: pd.DataFrame, old: pd.DataFrame) -> pd.DataFrame:
    """Fresh discovery wins on availability; the old ledger wins on transfer
    outcomes; vanished target versions are kept and flagged."""
    old = old.set_index("target_id")
    fresh = fresh.set_index("target_id")
    keep = old[old["status"].isin(_TRANSFER_STATUSES)]
    common_ids = fresh.index.intersection(keep.index)
    fresh.loc[common_ids, _TRANSFER_COLS] = keep.loc[common_ids, _TRANSFER_COLS]
    gone = old.loc[old.index.difference(fresh.index)].copy()
    gone["missing_upstream"] = True
    merged = pd.concat([fresh, gone]).reset_index()
    return common.coerce_ledger_dtypes(merged.reindex(columns=common.LEDGER_COLS))
