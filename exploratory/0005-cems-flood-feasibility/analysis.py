"""Feasibility probe: scraping ALL historical Copernicus EMS Rapid Mapping
flood activations (2012 -> present).

Standalone by design — talks only to public CEMS endpoints, writes only to
--work-dir (default /tmp/gie_cems_flood_poc). No repo pipeline or blob I/O.

Stages (each caches its output as parquet in the work dir):

  inventory        Comprehensive activation list from BOTH portals:
                   - new portal backend via ocha-lens (EMSR656+, 2023+)
                   - archive portal DRF API (EMSR001+, full history)
  legacy-manifest  Crawl every legacy (< EMSR656) flood activation page on the
                   archive portal -> one row per product vector-zip link.
  new-manifest     ocha-lens get_products() for every new-portal flood
                   activation -> delivered-product manifest.
  poc              Stratified sample (~3 activations/year, 2012-2023): download
                   one delineation zip each, locate the flood-extent layer
                   across all naming eras, read it, compute basic metrics.
  selective        Measure selective download: HTTP range-read ONLY the extent
                   + coverage members out of remote zips (both hosts are S3)
                   and compare bytes transferred vs the full zip. Needs the
                   remotezip package: add `--with remotezip` to the uv run.

Run:  uv run --group etl python exploratory/0005-cems-flood-feasibility/analysis.py [--stage all]
"""

from __future__ import annotations

import argparse
import re
import time
import warnings
import zipfile
from pathlib import Path

import geopandas as gpd
import ocha_lens as lens
import pandas as pd
import requests
from bs4 import BeautifulSoup

ARCHIVE_API = "https://mapping.emergency.copernicus.eu/activations/api/activations/"
ARCHIVE_PAGE = "https://mapping.emergency.copernicus.eu/activations/{code}/"
NEW_PORTAL_MIN = 656  # first EMSR number served by the new-portal backend

# Flood-extent layer name patterns across all CEMS naming eras (casefolded
# substring match on the .shp basename). Era boundaries are approximate.
EXTENT_PATTERNS = (
    "observedeventa",  # 2019+ camelCase, incl. new portal
    "crisis_information_poly",  # ~2014-2016
    # 2012-2013 ESRI era is a zoo (Crisis_event_A, Event_A_M, ...) and
    # ~2017-2018 uses observed_event_a; "_event_a" catches all of them.
    "_event_a",
)
# Present only in some 2025+ DEL products; supplementary, not the primary extent.
SUPPLEMENTARY_PATTERNS = ("maximumfloodextenta", "modelledeventa", "flooddeptha")

# Coverage layers ("what was actually observed"), needed to tell not-flooded
# from not-analysed; era-specific names.
COVERAGE_PATTERNS = (
    "areaofinteresta",
    "area_of_interest",
    "imagefootprinta",
    "notanalyseda",
    "general_information_poly",
    "sensor_metadata",
)

session = requests.Session()
session.headers["User-Agent"] = "Mozilla/5.0 (compatible; OCHA-CHD CEMS flood probe)"


# ---------------------------------------------------------------------------
# Stage 1: inventory
# ---------------------------------------------------------------------------


def fetch_archive_activations() -> pd.DataFrame:
    """Full historical activation list from the archive portal DRF API."""
    rows: list[dict] = []
    url: str | None = f"{ARCHIVE_API}?format=json&limit=500"
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


def stage_inventory(work: Path) -> pd.DataFrame:
    new = lens.cems.get_activations()
    archive = fetch_archive_activations()
    new.to_parquet(work / "new_portal_activations.parquet")
    archive.to_parquet(work / "archive_activations.parquet")

    fl_new = set(new.loc[new["category"].str.casefold() == "flood", "code"])
    fl_arc = archive[archive["category.slug"] == "flood"].copy()
    fl_arc["num"] = fl_arc["code"].str.extract(r"^EMSR(\d+)$")[0].astype("Int64")

    # cross-validation: for the overlap era the two portals must agree exactly
    arc_new_era = set(fl_arc.loc[fl_arc["num"] >= NEW_PORTAL_MIN, "code"])
    if arc_new_era != fl_new:
        raise RuntimeError(
            f"Portal disagreement for EMSR>={NEW_PORTAL_MIN}: "
            f"only-archive={sorted(arc_new_era - fl_new)} "
            f"only-new={sorted(fl_new - arc_new_era)}"
        )

    emsn = fl_arc[fl_arc["num"].isna()]
    fl_arc = fl_arc[fl_arc["num"].notna()]
    yr = pd.to_datetime(fl_arc["activationTime"]).dt.year
    print(f"archive total activations: {len(archive)}")
    print(f"flood activations (EMSR): {len(fl_arc)}  ({yr.min()}-{yr.max()})")
    print(f"  legacy (< EMSR{NEW_PORTAL_MIN}): {(fl_arc['num'] < NEW_PORTAL_MIN).sum()}")
    print(f"  new portal: {len(fl_new)} (portals agree)")
    print(f"  excluded flood-category EMSN (Risk & Recovery svc): {len(emsn)}")
    print("floods per year:\n", yr.value_counts().sort_index().to_string())
    return fl_arc


# ---------------------------------------------------------------------------
# Stage 2: legacy manifest (archive portal HTML)
# ---------------------------------------------------------------------------


def parse_activation_page(code: str) -> pd.DataFrame:
    """One row per product download link on an archive activation page."""
    r = session.get(ARCHIVE_PAGE.format(code=code), timeout=60)
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


def stage_legacy_manifest(work: Path) -> pd.DataFrame:
    arc = pd.read_parquet(work / "archive_activations.parquet")
    fl = arc[arc["category.slug"] == "flood"].copy()
    fl["num"] = fl["code"].str.extract(r"^EMSR(\d+)$")[0].astype("Int64")
    legacy = fl[fl["num"].notna() & (fl["num"] < NEW_PORTAL_MIN)].sort_values("num")

    frames, empty = [], []
    for _, act in legacy.iterrows():
        df = parse_activation_page(act["code"])
        if len(df):
            frames.append(df)
        else:
            # Known archive gap: a few pre-2023 activations were never migrated
            # (products exist per metadata but the archive page is empty).
            empty.append((act["code"], int(act["n_products"])))
        time.sleep(0.2)

    manifest = pd.concat(frames, ignore_index=True)
    manifest.to_parquet(work / "legacy_flood_manifest.parquet")
    print(f"legacy floods crawled: {len(legacy)}; with links: {manifest['code'].nunique()}")
    print(f"zip links: {len(manifest)}")
    print(f"EMPTY pages (code, n_products per API): {empty}")
    return manifest


# ---------------------------------------------------------------------------
# Stage 3: new-portal manifest (ocha-lens)
# ---------------------------------------------------------------------------


def stage_new_manifest(work: Path) -> pd.DataFrame:
    new = pd.read_parquet(work / "new_portal_activations.parquet")
    codes = sorted(new.loc[new["category"].str.casefold() == "flood", "code"])
    frames = []
    for code in codes:
        p = lens.cems.get_products(code)
        p["code"] = code
        frames.append(p)
    manifest = pd.concat(frames, ignore_index=True)
    manifest.to_parquet(work / "new_flood_manifest.parquet")
    delivered = manifest[manifest["download_url"].notna()]
    print(f"new-portal floods: {len(codes)}; manifest rows: {len(manifest)}")
    print(
        f"delivered zips: {len(delivered)} by type: "
        f"{delivered['product_type'].value_counts().to_dict()}"
    )
    no_delivery = sorted(set(codes) - set(delivered["code"]))
    print(f"activations with nothing delivered (all status N): {no_delivery}")
    return manifest


# ---------------------------------------------------------------------------
# Stage 4: PoC — era-spanning extent-layer extraction
# ---------------------------------------------------------------------------


def find_extent_layers(names: list[str]) -> list[str]:
    return [
        n
        for n in names
        if n.lower().endswith(".shp") and any(p in Path(n).name.lower() for p in EXTENT_PATTERNS)
    ]


def inspect_product_zip(fn: Path) -> dict:
    """Locate + read the flood-extent layer in one product zip."""
    names = zipfile.ZipFile(fn).namelist()
    hits = find_extent_layers(names)
    rec: dict = {"n_shp": sum(n.lower().endswith(".shp") for n in names)}
    if not hits:
        # Distinguish absence from failure: monitoring products where the
        # flood has receded (or the image was void) legitimately ship without
        # an event layer — report that state, don't invent one.
        rec.update(status="NO_EXTENT_LAYER", features=None, area_km2=None)
        return rec
    g = gpd.read_file(f"zip://{fn}!{hits[0]}")
    area_km2 = g.to_crs("EPSG:6933").union_all().area / 1e6
    rec.update(
        status="OK",
        layer=Path(hits[0]).name,
        features=len(g),
        crs=str(g.crs),
        area_km2=round(area_km2, 1),
    )
    return rec


def stage_poc(work: Path, per_year: int = 3) -> pd.DataFrame:
    dl = work / "poc_zips"
    dl.mkdir(exist_ok=True)
    m = pd.read_parquet(work / "legacy_flood_manifest.parquet")
    m = m[m["url"].str.contains("vector", case=False)].copy()
    m["year"] = pd.to_datetime(m["delivery"], errors="coerce").dt.year
    m["is_delin"] = m["title"].fillna("").str.contains("Delineation|First Estimate", case=False)

    picks = []
    for _, grp in m.groupby("year"):
        pool = grp[grp["is_delin"]] if grp["is_delin"].any() else grp
        codes = (
            pool["code"]
            .drop_duplicates()
            .sample(min(per_year, pool["code"].nunique()), random_state=42)
        )
        picks.extend(pool[pool["code"] == c].iloc[0] for c in codes)

    results = []
    for row in picks:
        fn = dl / row["url"].rsplit("/", 1)[-1]
        if not fn.exists():
            r = session.get(row["url"], timeout=300)
            r.raise_for_status()
            fn.write_bytes(r.content)
        rec = {"code": row["code"], "year": row["year"], "file": fn.name}
        rec.update(inspect_product_zip(fn))
        results.append(rec)
        print(f"  {row['code']} ({row['year']:.0f}) -> {rec['status']}")

    res = pd.DataFrame(results)
    res.to_csv(work / "poc_results.csv", index=False)
    ok = (res["status"] == "OK").sum()
    print(f"\nextent layer found+read: {ok}/{len(res)}")
    print(res[res["status"] != "OK"].to_string())
    return res


# ---------------------------------------------------------------------------
# Stage 5: selective download via HTTP range requests
# ---------------------------------------------------------------------------


def stage_selective(work: Path) -> pd.DataFrame:
    """Range-read only extent+coverage members from remote zips (no full
    download) and measure the bytes saved. Both zip hosts sit on S3, which
    honors Range; the new backend 302s to a presigned S3 URL first."""
    try:
        from remotezip import RemoteZip
    except ImportError as e:
        raise ImportError(
            "stage 'selective' needs the remotezip package - rerun as "
            "`uv run --group etl --with remotezip python ...`"
        ) from e

    import tempfile

    legacy = pd.read_parquet(work / "legacy_flood_manifest.parquet")
    legacy = legacy[legacy["url"].str.contains("vector", case=False)].copy()
    legacy["year"] = pd.to_datetime(legacy["delivery"], errors="coerce").dt.year
    new = pd.read_parquet(work / "new_flood_manifest.parquet")
    new_del = new[(new["product_type"] == "DEL") & new["download_url"].notna()]

    urls = [legacy[legacy["year"] == y].iloc[0]["url"] for y in (2012, 2016, 2018, 2022)] + [
        new_del.sort_values("delivery_time").iloc[0]["download_url"],
        new_del.sort_values("delivery_time").iloc[-1]["download_url"],
    ]

    wanted_pats = EXTENT_PATTERNS + COVERAGE_PATTERNS
    shp_parts = (".shp", ".dbf", ".shx", ".prj")
    results = []
    for url in urls:
        # resolve the new-backend redirect so range requests hit S3 directly
        final = session.head(url, allow_redirects=True, timeout=60).url
        with RemoteZip(final, headers=dict(session.headers)) as z:
            infos = z.infolist()
            full = sum(i.compress_size for i in infos)
            members = [
                i
                for i in infos
                if i.filename.lower().endswith(shp_parts)
                and any(p in Path(i.filename).name.lower() for p in wanted_pats)
            ]
            sel = sum(i.compress_size for i in members)
            extent_shp = [i.filename for i in members if find_extent_layers([i.filename])]
            n_feats = None
            if extent_shp:  # verify the fetched members reconstruct a layer
                stem = extent_shp[0][:-4]
                with tempfile.TemporaryDirectory() as td:
                    for ext in shp_parts:
                        if stem + ext in z.namelist():
                            (Path(td) / f"layer{ext}").write_bytes(z.read(stem + ext))
                    n_feats = len(gpd.read_file(Path(td) / "layer.shp"))
        name = url.rsplit("/", 1)[-1]
        results.append(
            {
                "file": name,
                "full_mb": round(full / 1e6, 2),
                "selective_mb": round(sel / 1e6, 2),
                "extent_features": n_feats,
            }
        )
        print(f"  {name}: {full / 1e6:5.1f} -> {sel / 1e6:5.2f} MB, feats={n_feats}")

    res = pd.DataFrame(results)
    res.to_csv(work / "selective_results.csv", index=False)
    frac = res["selective_mb"].sum() / res["full_mb"].sum()
    print(f"\nselective transfer: {frac:.1%} of full-zip bytes")
    return res


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--stage",
        default="all",
        choices=["all", "inventory", "legacy-manifest", "new-manifest", "poc", "selective"],
    )
    ap.add_argument("--work-dir", default="/tmp/gie_cems_flood_poc", type=Path)
    args = ap.parse_args(argv)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    warnings.filterwarnings("ignore", message=".*shapely.*|.*union_all.*")

    stages = {
        "inventory": stage_inventory,
        "legacy-manifest": stage_legacy_manifest,
        "new-manifest": stage_new_manifest,
        "poc": stage_poc,
        "selective": stage_selective,  # opt-in: extra dep (remotezip)
    }
    todo = [s for s in stages if s != "selective"] if args.stage == "all" else [args.stage]
    for name in todo:
        print(f"\n===== stage: {name} =====")
        stages[name](args.work_dir)


if __name__ == "__main__":
    main()
