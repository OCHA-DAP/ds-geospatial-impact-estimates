"""Full as-delivered damaged buildings per product from gold building_flags (OSU pinned v0)."""
import sys, json
sys.path.insert(0, "exploratory/paper/artefacts/lib")
import gie_paper as gp
from pathlib import Path

CAP = 12000
COLS = [("ms_dmg","MS"), ("sar_dmg","IMPACT"), ("osu_dmg","OSU"),
        ("debris_dmg","UNEP"), ("list_dmg","LIST"), ("uh_dmg","UH")]
df = gp.building_flags(columns=["lon","lat"] + [c for c,_ in COLS])
out, counts = [], {}
for col, name in COLS:
    d = df[df[col] == 1]
    counts[name] = len(d)
    s = d.sample(min(CAP, len(d)), random_state=0)
    out.append([[round(x,4), round(y,4)] for x, y in zip(s.lon, s.lat)])
    print(f"{name}: {len(d):,} delivered flags, {len(out[-1]):,} exported")
outp = Path(__file__).parent / "asdel.js"
outp.write_text("const ASDEL = " + json.dumps(out, separators=(",",":")) + ";\n")
print("counts:", counts, "| KB:", outp.stat().st_size//1024)
