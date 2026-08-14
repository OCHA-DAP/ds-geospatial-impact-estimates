"""Loader: MapSwipe/HOT crowd validation of AI damage detections (VEN) — re-runnable.

HOT ran a MapSwipe campaign (June-July 2026) where volunteers graded AI-flagged damage
locations ("Validate Footprints - Damage Area Assessment ..." projects): per ~50 m H3 task,
0 = No damage / 1 = Yes damaged-destroyed / 2 = Not sure. Tasks were seeded from Microsoft
AI4G and HOT fAIr detections (per-task `sources` column), so this is a FALSE-ALARM reference
(precision side) — volunteers never looked where no AI flagged, so it cannot measure misses.
See exploratory/paper/artefacts/RQ7-mapswipe-validation/NOTES.md for the value demo.

Lands, exactly as received (ADM-0003):
  bronze/source=mapswipe/adm0=VE/project=<id>/  agg_results_by_task_<id>_geom.geojson.gz,
                                                tasks_<id>.csv.gz, results_<id>.csv.gz
  bronze/source=mapswipe/adm0=VE/hdx/           HOT's HDX synthesis geojsons (provenance;
                                                its binary verdict collapses "No damage"
                                                into "uncertain" — analyse the RAW exports)
  bronze/source=mapswipe/adm0=VE/projects.json  manifest: id, name, status, answer-option
                                                labels (the 0/1/2 meanings), asset URLs

Re-running refreshes everything in place — MapSwipe re-exports as projects accrue votes
(several were still ongoing in July 2026), so this loader doubles as the update path.

`--project <id>` (repeatable) ingests only the named project(s): additive — other
projects' bronze files are not re-downloaded or touched, the manifest is merged rather
than rewritten, and the HDX synthesis is skipped. Use this to land a new campaign round
(e.g. 3248, the post-freeze Catia La Mar round 2) without refreshing the frozen rounds
in place.

Run: uv run --group etl python pipelines/ingest_mapswipe.py [--project 3248]
"""

from __future__ import annotations

import argparse
import json

import ocha_stratus as stratus
import requests

from gie import events, ledger
from gie.config import load_settings

GRAPHQL = "https://backend.mapswipe.org/graphql/"
NAME_FILTER = "Damage Area Assessment"  # the Venezuela EQ validation campaign
HDX = "https://data.humdata.org/api/3/action/package_show?id={}"
HDX_SLUG = "venezuela-m-7-5-earthquake-building-damage-assessment"
SOURCE = "mapswipe"
ADM0 = "VE"
STAGE = "dev"
EVENT = "20260624-ve-earthquake"  # validated against events.yaml in main()

PROJECTS_QUERY = """
{ publicProjects(filters:{name:"%s"}, pagination:{limit:60,offset:0}){ results{
    id name status progressStatus
    projectTypeSpecifics { ... on ValidateProjectPropertyType {
        customOptions { value title description } } }
    exportAggregatedResultsWithGeometry{ file{ url } }
    exportTasks{ file{ url } }
    exportResults{ file{ url } }
} } }
""" % NAME_FILTER


def _gql(query: str) -> dict:
    # GET, not POST: the endpoint is Django-CSRF-protected for POST but open for GET.
    r = requests.get(GRAPHQL, params={"query": query}, timeout=60)
    r.raise_for_status()
    out = r.json()
    if out.get("errors"):
        raise RuntimeError(f"MapSwipe GraphQL: {out['errors']}")
    return out["data"]


def main(project_ids: list[str] | None = None) -> None:
    events.require_event(EVENT)
    settings = load_settings(STAGE)
    base = ("bronze", f"source={SOURCE}", f"adm0={ADM0}")

    projects = _gql(PROJECTS_QUERY)["publicProjects"]["results"]
    if project_ids:
        missing = set(project_ids) - {p["id"] for p in projects}
        if missing:
            raise RuntimeError(f"requested project(s) not found under the "
                               f"'{NAME_FILTER}' campaign: {sorted(missing)}")
        projects = [p for p in projects if p["id"] in project_ids]
    manifest, n_files = [], 0
    for p in projects:
        assets = {}
        for key, label in (("exportAggregatedResultsWithGeometry", "agg_geom"),
                           ("exportTasks", "tasks"), ("exportResults", "results")):
            url = ((p.get(key) or {}).get("file") or {}).get("url")
            if not url:
                continue
            fname = url.rsplit("/", 1)[1]
            raw = requests.get(url, timeout=120).content
            dest = settings.blob_path(*base, f"project={p['id']}", fname, event=EVENT)
            stratus.upload_blob_data(raw, dest, stage=STAGE, container_name=settings.container)
            assets[label] = url
            n_files += 1
        manifest.append({
            "id": p["id"], "name": p["name"], "status": p["status"],
            "progress": p["progressStatus"],
            "options": (p.get("projectTypeSpecifics") or {}).get("customOptions"),
            "assets": assets,
        })
        print(f"  project {p['id']}: {len(assets)} files  ({p['name'][:60]}…)")

    if project_ids:
        print("  (--project mode: HDX synthesis not re-downloaded)")
    else:
        # HOT's HDX synthesis (citable provenance; verdict = accepted/uncertain only)
        rs = requests.get(HDX.format(HDX_SLUG), timeout=60).json()["result"]["resources"]
        hdx_files = []
        for r in rs:
            if r["format"].lower() != "geojson":
                continue
            raw = requests.get(r["url"], timeout=120).content
            dest = settings.blob_path(*base, "hdx", r["name"], event=EVENT)
            stratus.upload_blob_data(raw, dest, stage=STAGE, container_name=settings.container)
            hdx_files.append(r["name"])
            n_files += 1
        print(f"  hdx: {', '.join(hdx_files)}")

    mdest = settings.blob_path(*base, "projects.json", event=EVENT)
    if project_ids:
        # merge into the existing manifest — a filtered run must not shrink it
        prior = json.loads(stratus.load_blob_data(mdest, stage=STAGE,
                                                  container_name=settings.container))
        merged = {p["id"]: p for p in prior}
        merged.update({p["id"]: p for p in manifest})
        manifest = sorted(merged.values(), key=lambda p: p["id"])
    stratus.upload_blob_data(json.dumps(manifest, indent=1).encode(), mdest,
                             stage=STAGE, container_name=settings.container)

    root = settings.blob_path(*base, event=EVENT)
    print(f"bronze <- {root}  ({len(projects)} projects, {n_files} files + manifest)")
    scope = (f"filtered additive ingest of project(s) {', '.join(project_ids)}"
             if project_ids else f"{len(projects)} Validate projects + HDX synthesis")
    ledger.record(
        SOURCE,
        "bronze",
        "MapSwipe/HOT crowd validation of AI damage flags (0/1/2 votes per ~50 m H3 task)",
        root,
        f"{scope}; false-alarm reference "
        f"(MS AI4G + fAIr seeds only, no miss detection); re-run to refresh",
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", action="append", default=None, metavar="ID",
                    help="ingest only this project id (repeatable); additive — other "
                         "projects' bronze files are left untouched")
    main(ap.parse_args().project)
