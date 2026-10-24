#!/usr/bin/env python3
"""Copy the demo service's whitelisted Juliet cases into service/juliet/ (D-0061).

Picks up to 20 cases that were verified in the Juliet smoke run (cases/juliet/selection.json,
runs/e1_juliet60_v1), balanced across CWE-401/415/416, and copies their case JSON, source
files and Juliet's testcasesupport files. NIST's Juliet test suite is a US-government work in
the public domain; only these few files are redistributed.
"""

from __future__ import annotations

import json
import shutil
import sys

from leakproof.cases.juliet import JULIET, SUPPORT
from leakproof.config import REPO_ROOT, RUNS_DIR

OUT = REPO_ROOT / "service" / "juliet"
PER_CWE = {"401": 8, "415": 6, "416": 6}


def main() -> int:
    picked = []
    for cwe, k in PER_CWE.items():
        ids = sorted(
            p.stem
            for p in (RUNS_DIR / "e1_juliet60_v1").glob(f"CWE{cwe}_*.json")
            if json.loads(p.read_text())["verdict"] == "verified"
        )
        picked += ids[:k]
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "cases").mkdir(parents=True)
    for f in SUPPORT:
        dest = OUT / "C" / "testcasesupport" / f
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(JULIET / "testcasesupport" / f, dest)
    for cid in picked:
        data = json.loads((REPO_ROOT / "cases" / "juliet" / f"{cid}.json").read_text())
        (OUT / "cases" / f"{cid}.json").write_text(json.dumps(data, indent=1) + "\n")
        for f in data["files"]:
            dest = OUT / "C" / data["dir"] / f
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(JULIET / data["dir"] / f, dest)
    (OUT / "cases.txt").write_text("\n".join(picked) + "\n")
    print(f"exported {len(picked)} cases to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
