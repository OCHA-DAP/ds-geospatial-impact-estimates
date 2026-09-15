"""Sign the archive's current outputs off into frozen/ (ADR-0032).

Copies each file listed in frozen/MANIFEST.csv from its `source` path under artefacts/ and rewrites
the manifest line: file, source, producing_commit (HEAD short sha), sha256, signed_off (today).
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
    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, cwd=PAPER).strip()
    today = datetime.date.today().isoformat()
    changed = []
    for i, r in m.iterrows():
        src = os.path.join(PAPER, r.source)
        if not os.path.exists(src):
            raise FileNotFoundError(f"vendor: archive output missing: {r.source} (run `snakemake heavy` first)")
        dst = os.path.join(FROZEN, r.file)
        new_hash = hashlib.sha256(open(src, "rb").read()).hexdigest()
        if new_hash != r.sha256:
            shutil.copy2(src, dst)
            m.loc[i, ["producing_commit", "sha256", "signed_off"]] = [commit, new_hash, today]
            changed.append(r.file)
    m.to_csv(MANIFEST, index=False)
    print(f"vendor: {len(changed)} file(s) re-signed" + (": " + ", ".join(changed) if changed else " (frozen/ already matches the archive)"))


if __name__ == "__main__":
    main()
