#!/usr/bin/env python3
"""Pick the Juliet smoke set: 30 x CWE-401, 15 x CWE-415, 15 x CWE-416 (kickoff 3.5).

A Juliet test case can span several files (`..._51a.c`, `..._51b.c`; `..._81_bad.cpp`,
`..._81a.cpp`, `..._81.h`); files are grouped by their `<name>_<flow>` stem. Selection is
deterministic and greedy for diversity across functional variant, flow variant and language.

Excluded on purpose:
- flow variant 12: `globalReturnsTrueOrFalse()` picks bad/good at random, so not reproducible;
- `malloc_realloc_*`: leaks only when realloc fails, which a sanitizer run never exercises.

Writes cases/juliet/selection.json. Usage: uv run python scripts/juliet_select.py
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JULIET = Path.home() / ".cache" / "leakproof" / "juliet" / "C"
QUOTAS = {"401": 30, "415": 15, "416": 15}
EXPECTED_KIND = {"401": "leak", "415": "double-free", "416": "use-after-free"}
_STEM = re.compile(
    r"^(?P<base>CWE(?P<cwe>\d+)_\w+?__(?P<func>\w+)_(?P<flow>\d{2}))(?:[a-z]|_bad|_good\w*)?$"
)
EXCLUDED_FLOWS = {"12"}
EXCLUDED_FUNCS = re.compile(r"^malloc_realloc_")


def discover(cwe: str) -> list[dict]:
    (cwe_dir,) = (JULIET / "testcases").glob(f"CWE{cwe}_*")
    groups: dict[str, dict] = {}
    for path in sorted(cwe_dir.rglob("*")):
        if path.suffix not in {".c", ".cpp", ".h"} or path.name.startswith("main"):
            continue
        m = _STEM.match(path.stem)
        if not m:
            continue
        g = groups.setdefault(
            m["base"],
            {
                "id": m["base"],
                "cwe": f"CWE-{cwe}",
                "functional_variant": m["func"],
                "flow_variant": m["flow"],
                "dir": str(path.parent.relative_to(JULIET)),
                "files": [],
            },
        )
        g["files"].append(path.name)
    out = []
    for g in groups.values():
        sources = [f for f in g["files"] if f.endswith((".c", ".cpp"))]
        if not sources:
            continue
        g["lang"] = "c++" if any(f.endswith(".cpp") for f in sources) else "c"
        g["expected_kind"] = EXPECTED_KIND[cwe]
        out.append(g)
    return out


def select(cands: list[dict], k: int, rng: random.Random) -> list[dict]:
    pool = [
        c
        for c in cands
        if c["flow_variant"] not in EXCLUDED_FLOWS
        and not EXCLUDED_FUNCS.match(c["functional_variant"])
    ]
    rng.shuffle(pool)
    funcs: Counter[str] = Counter()
    flows: Counter[str] = Counter()
    langs: Counter[str] = Counter()
    chosen: list[dict] = []
    for _ in range(min(k, len(pool))):
        best = min(
            pool,
            key=lambda c: (
                funcs[c["functional_variant"]],
                flows[c["flow_variant"]],
                langs[c["lang"]],
            ),
        )
        pool.remove(best)
        chosen.append(best)
        funcs[best["functional_variant"]] += 1
        flows[best["flow_variant"]] += 1
        langs[best["lang"]] += 1
    return sorted(chosen, key=lambda c: c["id"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=112)
    ap.add_argument("--out", type=Path, default=ROOT / "cases" / "juliet" / "selection.json")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    selection = []
    for cwe, k in QUOTAS.items():
        cands = discover(cwe)
        picked = select(cands, k, rng)
        langs = Counter(c["lang"] for c in picked)
        print(
            f"CWE-{cwe}: {len(cands)} cases -> {len(picked)} picked "
            f"({langs['c']} C, {langs['c++']} C++, "
            f"{len({c['functional_variant'] for c in picked})} functional variants, "
            f"{len({c['flow_variant'] for c in picked})} flow variants)"
        )
        selection.extend(picked)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"seed": args.seed, "cases": selection}, indent=1) + "\n")
    print(f"wrote {args.out} ({len(selection)} cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
