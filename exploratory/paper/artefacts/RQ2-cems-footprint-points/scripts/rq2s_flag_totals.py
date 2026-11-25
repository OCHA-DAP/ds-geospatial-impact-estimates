"""rq2s — total flags per product on the shared base, versus flags inside any CEMS extent.

Feeds the brief's 'share of each product's flags that no reference can score' sentence
(ADR-0030 frame: flags per gp.building_flags(), so Microsoft is the 1:1-mapped set).
Writes rq2s_flag_totals.csv: product, total_flags, in_cems_extent, share_outside.
"""
import os, sys
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
import gie_paper as gp  # noqa: E402

FLAGS = {"MS": "ms_dmg", "IMPACT": "sar_dmg", "OSU": "osu_dmg", "UH": "uh_dmg", "LIST": "list_dmg", "UNEP": "debris_dmg"}

def main():
    df = gp.building_flags(columns=list(FLAGS.values()))
    rq2i = pd.read_csv(os.path.join(HERE, "..", "rq2i_per_aoi_scorecard.csv"))
    asd = rq2i[rq2i.aoi == "ALL (as delivered)"].drop_duplicates("product").set_index("product")
    rows = []
    for p, col in FLAGS.items():
        total = int((df[col].to_numpy(dtype="float64", na_value=0.0) == 1).sum())
        inside = int(asd.loc[p, "n_flags"])
        if inside > total:
            raise RuntimeError(f"{p}: in-extent flags {inside} exceed total {total}")
        rows.append(dict(product=p, total_flags=total, in_cems_extent=inside, share_outside=round(1 - inside / total, 3)))
        print(rows[-1])
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "..", "rq2s_flag_totals.csv"), index=False)
    print("wrote rq2s_flag_totals.csv")

if __name__ == "__main__":
    main()
