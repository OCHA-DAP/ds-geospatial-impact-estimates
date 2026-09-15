"""Export each product's analysed extent (plus CEMS + core) as simplified GeoJSON for the PoC."""
import os, sys, json
sys.path.insert(0, "exploratory/paper/artefacts/lib")
import geopandas as gpd, h3
import gie_paper as gp
from shapely.geometry import Polygon
from shapely.ops import unary_union

def uh_aoi():
    g = gp._read_pq("silver", "source=uh", "adm0=VE", "footprints.parquet")
    cells = {h3.latlng_to_cell(p.y, p.x, 9) for p in g.geometry.representative_point()}
    dil = set()
    for c in cells: dil.update(h3.grid_disk(c, 1))
    polys = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in dil]
    return gp.dissolve_union(gpd.GeoDataFrame(geometry=[unary_union(polys)], crs=4326))

aois = {
    "Microsoft": gp.dissolve_union(gp.microsoft_aoi()),
    "IMPACT": gp.dissolve_union(gp.impact_v2_aoi()),
    "OSU": gp.dissolve_union(gp.osu_aoi()),
    "UH": uh_aoi(),
    "LIST": gp.dissolve_union(gp._read_pq("silver", "source=list", "adm0=VE", "analysed_extent.parquet")),
}
cems = gp.to_metric(gp.cems_extent().query("is_latest"))
cems_u = cems.geometry.make_valid().union_all()
core = cems_u
for a in aois.values(): core = core.intersection(a)

feats = []
def add(name, geom_metric, kind):
    g = gpd.GeoSeries([geom_metric], crs=gp.METRIC if hasattr(gp, "METRIC") else 32619)
    g = g.simplify(150).to_crs(4326)
    feats.append({"type": "Feature", "properties": {"name": name, "kind": kind},
                  "geometry": json.loads(g.to_json())["features"][0]["geometry"]})
for nm, a in aois.items(): add(nm, a, "product")
add("CEMS", cems_u, "cems")
add("core", core, "core")
out = {"type": "FeatureCollection", "features": feats}
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "extents.js"), "w").write(
    "const EXTENTS = " + json.dumps(out, separators=(",", ":")) + ";\n")
print("wrote extents.js:", [f["properties"]["name"] for f in feats],
      "| KB:", round(os.path.getsize(os.path.join(os.path.dirname(os.path.abspath(__file__)), "extents.js"))/1e3))
