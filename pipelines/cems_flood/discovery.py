"""Build the harvest ledger: one row per CEMS flood product zip we intend to
archive, PLUS explicit rows for everything we know exists but cannot get —
the ledger is the transparency record, so absence is stated, never implied.

Sources (see exploratory/0005-cems-flood-feasibility for the evidence):
  - archive portal (mapping.emergency.copernicus.eu): all activations 2012->,
    product links parsed from each activation's server-rendered page
  - new portal (EMSR656+, Mar 2023->): via ocha_lens.cems.get_products()

Statuses set here (harvest.py owns the transfer statuses):
  pending                   has a URL, will be fetched
  excluded_ref              REF (pre-event reference map) — inventoried, not fetched
  unavailable_not_migrated  legacy page empty though API metadata says products exist
  unavailable_no_products   activation delivered nothing (n_products == 0)
  unavailable_status_N      new-portal product closed without delivery
  unavailable_no_url        new-portal product not (yet) delivered, not closed

Re-running is the backfill mechanism: fresh discovery is merged onto the
existing ledger — transfer outcomes are preserved, newly appeared targets
become pending, and targets that vanished upstream are kept and flagged
``missing_upstream`` rather than dropped.

Run:  uv run --group etl --group api python pipelines/cems_flood/discovery.py [--work-dir ...]
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

import common
import ocha_lens as lens
import pandas as pd
from bs4 import BeautifulSoup

LEDGER_COLS = [
    "target_id",
    "code",
    "source",
    "aoi",
    "title",
    "product_class",
    "monitoring_number",
    "version_number",
    "delivery_time",
    "url",
    "basename",
    "blob_path",
    "status",
    "http_status",
    "error",
    "attempts",
    "attempted_at",
    "uploaded_at",
    "sha256",
    "size_bytes",
    "n_members",
    "missing_upstream",
]
# statuses that record a transfer outcome and must survive re-discovery
_TRANSFER_STATUSES = ("uploaded", "failed_download", "failed_upload")


def fetch_archive_activations(session) -> pd.DataFrame:
    rows: list[dict] = []
    url: str | None = f"{common.ARCHIVE_API}?format=json&limit=500"
    while url:
        r = session.get(url.replace("http://", "https://"), timeout=60)
        r.raise_for_status()
        data = r.json()
        rows.extend(data["results"])
        url = data["next"]
    df = pd.json_normalize(rows)
    df["countries"] = df["countries"].apply(
        lambda cs: "; ".join(c["short_name"] for c in cs) if len(cs) else None
    )
    return df


def parse_activation_page(session, code: str) -> pd.DataFrame:
    """One row per product zip link on an archive-portal activation page."""
    r = session.get(common.ARCHIVE_PAGE.format(code=code), timeout=60)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    aoi_names = {
        t["data-bs-target"].lstrip("#"): t.get_text(strip=True)
        for t in soup.select("a[id$='-tab'][data-bs-target]")
    }
    rows = []
    for pane in soup.select("div.tab-pane"):
        aoi = aoi_names.get(pane.get("id", ""), pane.get("id", ""))
        for card in pane.select("div.card"):
            title_el = card.select_one(".card-title")
            small = card.select_one(".card-text small")
            delivery = None
            if small:
                m = re.search(r"Delivery:\s*(.+)", small.get_text(strip=True))
                delivery = m.group(1) if m else None
            for a in card.select("a[href$='.zip']"):
                rows.append(
                    {
                        "code": code,
                        "aoi": aoi,
                        "title": title_el.get_text(strip=True) if title_el else None,
                        "delivery": delivery,
                        "url": a["href"],
                    }
                )
    return pd.DataFrame(rows)


def _unavailable_row(act: pd.Series, status: str) -> dict:
    return {
        "target_id": f"{act['code']}/__{status}__",
        "code": act["code"],
        "source": "archive",
        "status": status,
        "error": f"API metadata: n_aois={act['n_aois']} n_products={act['n_products']}",
    }


def build_legacy_targets(session, floods: pd.DataFrame) -> pd.DataFrame:
    """Crawl every legacy flood activation page -> target rows."""
    legacy = floods[floods["num"] < common.NEW_PORTAL_MIN].sort_values("num")
    rows: list[dict] = []
    for i, (_, act) in enumerate(legacy.iterrows()):
        links = parse_activation_page(session, act["code"])
        links = links[links["url"].str.contains("vector", case=False)] if len(links) else links
        if not len(links):
            status = (
                "unavailable_no_products" if act["n_products"] == 0 else "unavailable_not_migrated"
            )
            rows.append(_unavailable_row(act, status))
        for _, ln in links.iterrows():
            basename = unquote(Path(urlsplit(ln["url"]).path).name)
            cls = common.classify_title(ln["title"])
            rows.append(
                {
                    "target_id": f"{act['code']}/{basename}",
                    "code": act["code"],
                    "source": "archive",
                    "aoi": ln["aoi"],
                    "title": ln["title"],
                    "product_class": cls,
                    "delivery_time": ln["delivery"],
                    "url": ln["url"],
                    "basename": basename,
                    "blob_path": common.zip_blob_path(act["code"], basename),
                    "status": "excluded_ref" if cls == "REF" else "pending",
                }
            )
        if (i + 1) % 25 == 0:
            print(f"  archive pages: {i + 1}/{len(legacy)}")
        time.sleep(0.2)
    return pd.DataFrame(rows)


def build_new_targets(floods_new: list[str]) -> pd.DataFrame:
    """New-portal product manifests via ocha-lens -> target rows."""
    rows: list[dict] = []
    for code in sorted(floods_new):
        prods = lens.cems.get_products(code)
        for _, p in prods.iterrows():
            base = {
                "code": code,
                "source": "new_portal",
                "aoi": f"AOI{p['aoi_number']:02d} {p['aoi_name']}",
                "title": None,
                "product_class": p["product_type"],
                "monitoring_number": p["monitoring_number"],
                "version_number": p["version_number"],
                "delivery_time": p["delivery_time"],
            }
            if pd.notna(p["download_url"]):
                basename = unquote(Path(urlsplit(p["download_url"]).path).name)
                rows.append(
                    base
                    | {
                        "target_id": f"{code}/{basename}",
                        "url": p["download_url"],
                        "basename": basename,
                        "blob_path": common.zip_blob_path(code, basename),
                        "status": "excluded_ref" if p["product_type"] == "REF" else "pending",
                    }
                )
            else:
                status = "unavailable_status_N" if p["status_code"] == "N" else "unavailable_no_url"
                rows.append(
                    base
                    | {
                        "target_id": f"{code}/product_id={p['product_id']}",
                        "status": status,
                        "error": f"status_code={p['status_code']} feasible={p['feasible']}",
                    }
                )
    return pd.DataFrame(rows)


def merge_ledgers(fresh: pd.DataFrame, old: pd.DataFrame) -> pd.DataFrame:
    """Backfill-preserving merge: fresh discovery wins on availability, the
    old ledger wins on transfer outcomes; vanished targets are kept+flagged."""
    old = old.set_index("target_id")
    fresh = fresh.set_index("target_id")
    keep = old[old["status"].isin(_TRANSFER_STATUSES)]
    common_ids = fresh.index.intersection(keep.index)
    transfer_cols = [
        "status",
        "http_status",
        "error",
        "attempts",
        "attempted_at",
        "uploaded_at",
        "sha256",
        "size_bytes",
        "n_members",
    ]
    fresh.loc[common_ids, transfer_cols] = keep.loc[common_ids, transfer_cols]
    gone = old.loc[old.index.difference(fresh.index)].copy()
    gone["missing_upstream"] = True
    merged = pd.concat([fresh, gone]).reset_index()
    return merged


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", default="/tmp/gie_cems_flood_archive", type=Path)
    args = ap.parse_args(argv)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    session = common.make_session()

    print("fetching activation lists (both portals) ...")
    archive = fetch_archive_activations(session)
    new = lens.cems.get_activations()
    floods = archive[archive["category.slug"] == "flood"].copy()
    floods["num"] = floods["code"].str.extract(r"^EMSR(\d+)$")[0].astype("Int64")
    floods = floods[floods["num"].notna()]  # EMSN* = Risk & Recovery service, out of scope
    floods_new = new.loc[new["category"].str.casefold() == "flood", "code"].tolist()

    # the archive list is the comprehensive one; the new portal must be a subset
    arc_new_era = set(floods.loc[floods["num"] >= common.NEW_PORTAL_MIN, "code"])
    if arc_new_era != set(floods_new):
        raise RuntimeError(
            f"portal disagreement: only-archive={sorted(arc_new_era - set(floods_new))} "
            f"only-new={sorted(set(floods_new) - arc_new_era)}"
        )
    floods.to_parquet(args.work_dir / "activations.parquet")
    print(
        f"flood activations: {len(floods)} (legacy "
        f"{(floods['num'] < common.NEW_PORTAL_MIN).sum()}, new {len(floods_new)})"
    )

    print("building legacy targets (crawling archive pages) ...")
    legacy_targets = build_legacy_targets(session, floods)
    print("building new-portal targets (ocha-lens manifests) ...")
    new_targets = build_new_targets(floods_new)

    ledger = pd.concat([legacy_targets, new_targets], ignore_index=True)
    ledger = ledger.reindex(columns=LEDGER_COLS)
    ledger["missing_upstream"] = ledger["missing_upstream"].fillna(False)
    ledger["attempts"] = ledger["attempts"].fillna(0)
    # legacy rows carry delivery as strings, new-portal rows as Timestamps;
    # normalize (errors raise — an unparseable delivery is upstream drift)
    ledger["delivery_time"] = pd.to_datetime(ledger["delivery_time"], format="mixed")
    ledger = common.coerce_ledger_dtypes(ledger)

    dup = ledger[ledger["target_id"].duplicated(keep=False)]
    if len(dup):
        dup_urls = dup.groupby("target_id")["url"].nunique()
        if (dup_urls > 1).any():
            raise RuntimeError(f"basename collision with differing URLs:\n{dup}")
        ledger = ledger.drop_duplicates("target_id")

    ledger_path = args.work_dir / "products.parquet"
    if ledger_path.exists():
        old = pd.read_parquet(ledger_path)
        ledger = merge_ledgers(ledger, old)
        print(f"merged onto existing ledger ({len(old)} rows)")
    ledger.to_parquet(ledger_path)

    print(f"\nledger: {len(ledger)} rows -> {ledger_path}")
    print(ledger["status"].value_counts().to_string())
    print("\npending by product class:")
    print(ledger[ledger["status"] == "pending"]["product_class"].value_counts().to_string())


if __name__ == "__main__":
    main()
