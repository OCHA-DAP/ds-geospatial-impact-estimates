"""Smoke test: confirm the blob read path for parquet (silver) + gpkg (bronze) before
building the scorer. Prints counts/columns/CRS for the layers RQ1 needs. Non-destructive."""
from __future__ import annotations
import io, os, sys, tempfile
import geopandas as gpd
import ocha_stratus as stratus
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src"))
from gie.config import load_settings  # noqa: E402

s = load_settings("dev")
print("container:", s.container)


def read_pq(*parts, layer="silver"):
    path = s.blob_path(layer, *parts)
    raw = stratus.load_blob_data(path, stage="dev", container_name=s.container)
    return gpd.read_parquet(io.BytesIO(raw))


def read_gpkg(*parts, layer="bronze"):
    path = s.blob_path(layer, *parts)
    raw = stratus.load_blob_data(path, stage="dev", container_name=s.container)
    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as f:
        f.write(raw); tmp = f.name
    try:
        return gpd.read_file(tmp)
    finally:
        os.unlink(tmp)


# CEMS silver (points + blocks in one file, split by layer_type)
cems = read_pq("source=copernicus_ems", "adm0=VE", "builtup_damage.parquet")
print("\nCEMS builtup_damage:", len(cems), "crs", cems.crs)
print("  cols:", list(cems.columns))
print("  layer_type:", cems.layer_type.value_counts().to_dict())
print("  blocks(area) grades:", cems[cems.layer_type == "area"].ems_grade.value_counts().to_dict())

ext = read_pq("source=copernicus_ems", "adm0=VE", "analysed_extent.parquet")
print("\nCEMS analysed_extent:", len(ext), "cols", list(ext.columns))

ms = read_pq("source=microsoft", "adm0=VE", "footprints.parquet")
print("\nMicrosoft:", len(ms), "damaged", int(ms.damaged.sum()), "crs", ms.crs, "cols", list(ms.columns))

iv2 = read_pq("source=impact_initiatives", "adm0=VE", "building_damage.parquet")
print("\nIMPACT v2:", len(iv2), "crs", iv2.crs, "cols", list(iv2.columns))

osu = read_gpkg("source=osu", "adm0=VE", "EMSR884_damage_20260625_v0_damaged.gpkg")
print("\nOSU damaged (bronze gpkg):", len(osu), "crs", osu.crs, "cols", list(osu.columns))
osu_aoi = read_gpkg("source=osu", "adm0=VE", "EMSR884_analyzed_area_20260625_v0.gpkg")
print("OSU analyzed_area:", len(osu_aoi), "crs", osu_aoi.crs)
print("\nSMOKE OK")
