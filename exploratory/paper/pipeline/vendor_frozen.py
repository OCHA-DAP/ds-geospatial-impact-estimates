"""Sign the archive's current outputs off into frozen/ (ADR-0032).

Copies each file listed in frozen/MANIFEST.csv from its `source` path under artefacts/ and rewrites
the manifest line: file, source, producing_commit (the last commit that changed the source file in git, so a
file that was NOT re-run keeps its real provenance), sha256, signed_off (today).
Run only after an explicit `snakemake heavy`; the diff in git under frozen/ is the review record.

Usage: python pipeline/vendor_frozen.py   (from exploratory/paper)
"""
import datetime
import hashlib
import os
import shutil
import subprocess

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.join(HERE, "..")
FROZEN = os.path.join(PAPER, "frozen")
MANIFEST = os.path.join(FROZEN, "MANIFEST.csv")


def main():
    m = pd.read_csv(MANIFEST)
    def producing_commit(src):   # last commit touching the archive file; a copy made at HEAD is not a provenance
        out = subprocess.check_output(["git", "log", "-1", "--format=%h", "--", src], text=True, cwd=PAPER).strip()
        if not out:
            raise SystemExit(f"vendor: {src} has no git history; commit the archive output before signing it off")
        return out
    today = datetime.date.today().isoformat()
    changed = []
    for i, r in m.iterrows():
        src = os.path.join(PAPER, r.source)
        if not os.path.exists(src):
            raise FileNotFoundError(f"vendor: archive output missing: {r.source} (run `snakemake heavy` first)")
        dst = os.path.join(FROZEN, r.file)
        new_hash = hashlib.sha256(open(src, "rb").read()).hexdigest()
        m.loc[i, "producing_commit"] = producing_commit(r.source)   # provenance is a fact about the source, refreshed every run
        if new_hash != r.sha256:
            shutil.copy2(src, dst)
            m.loc[i, ["sha256", "signed_off"]] = [new_hash, today]
            changed.append(r.file)
    m.to_csv(MANIFEST, index=False)
    print(f"vendor: {len(changed)} file(s) re-signed" + (": " + ", ".join(changed) if changed else " (frozen/ already matches the archive)"))


if __name__ == "__main__":
    main()
