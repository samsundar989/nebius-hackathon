#!/usr/bin/env python3
"""Sanitizer silent is not fixed: counted from the run records (review #17 order 3, #18 A).

Unit: worker candidates. A candidate "silenced the sanitizer" when the reported crash no longer
reproduces on the PoC (gate check `patched` = pass; for CUDA, `sanitizer` = pass). Of those, it
counts how many a later gate check rejected, and, for the verified ones on real OSS-Fuzz bugs,
what the hand/semantic review against the developer's fix said. Writes site/data/silent.json and
prints the arithmetic for docs/NUMBERS.md.

scripts/silent_not_fixed.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter

from leakproof.config import REPO_ROOT

DATA = REPO_ROOT / "site" / "data"
ARVO = ("p3_arvo27_r1", "p3_arvo27_r2")
JULIET = ("e1_juliet60_v1", "p2_sandboxes_juliet3", "p4_juliet401x100_r1")
REVIEW_OK = ("equivalent", "different_but_correct")


def silenced(run: str) -> list[dict]:
    d = json.loads((DATA / "runs" / f"{run}.json").read_text())
    return [
        w | {"_case": c["case"]}
        for c in d["cases"]
        for w in c["workers"]
        if (w["checks"].get("patched") or {}).get("s") == "pass"
    ]


def head_to_head(ws: list[dict]) -> dict:
    """Bad patches each check would ship (review #22): bad = rejected by the gate or reviewed
    wrong. "Crash gone" ships every bad one; "crash gone + tests pass" ships the bad ones whose
    project tests passed, among those where the tests ran; Leakproof ships the verified wrong."""

    def bad(w: dict) -> bool:
        return w["verdict"] != "verified" or w.get("semantic") == "wrong"

    def shipped(w: dict) -> bool:
        return w["verdict"] == "verified" and w.get("semantic") == "wrong"

    tests = lambda w: (w["checks"].get("tests") or {}).get("s")  # noqa: E731
    tested = [w for w in ws if tests(w) in ("pass", "fail")]
    return {
        "all": {
            "patches": len(ws),
            "crash_gone_ships": sum(map(bad, ws)),
            "leakproof_ships": sum(map(shipped, ws)),
        },
        "tested": {
            "patches": len(tested),
            "crash_gone_tests_pass_ships": sum(bad(w) and tests(w) == "pass" for w in tested),
            "leakproof_ships": sum(map(shipped, tested)),
        },
        "bugs": len({w["_case"] for w in ws}),
    }


def main() -> int:
    arvo = {r: silenced(r) for r in ARVO}
    ws = [w for r in ARVO for w in arvo[r]]
    verdicts = Counter(w["verdict"] for w in ws)
    rejected = {v: n for v, n in verdicts.items() if v != "verified"}
    sem = Counter(w.get("semantic") for w in ws if w["verdict"] == "verified")
    wrong, defensive = sem["wrong"], sem["defensive"]
    not_fixes = sum(rejected.values()) + wrong
    jul = [w for r in JULIET for w in silenced(r)]
    cuda = json.loads((DATA / "cuda.json").read_text())
    cuda_c = [
        c
        for k, v in cuda.items()
        if not k.startswith("_")
        for c in v.get("candidates", [])
        if (c["checks"].get("sanitizer") or {}).get("status") == "pass"
    ]
    out = {
        "unit": "worker candidates",
        "arvo": {
            "runs": list(ARVO),
            "silenced": len(ws),
            "silenced_by_run": {r: len(arvo[r]) for r in ARVO},
            "rejected_by_gate": rejected,
            "rejected_total": sum(rejected.values()),
            "verified": verdicts["verified"],
            "review_of_verified": dict(sem),
            "correct": sum(sem[k] for k in REVIEW_OK),
            "wrong": wrong,
            "defensive": defensive,
            "not_fixes": not_fixes,
            "not_fixes_pct": round(100 * not_fixes / len(ws)),
            "caught_by_gate_pct": round(100 * sum(rejected.values()) / not_fixes),
            "head_to_head": head_to_head(ws),
        },
        "juliet": {
            "runs": list(JULIET),
            "silenced": len(jul),
            "verified": sum(w["verdict"] == "verified" for w in jul),
            "note": "synthetic NIST Juliet cases",
        },
        "cuda": {
            "silenced": len(cuda_c),
            "verified": sum(c["verdict"] == "verified" for c in cuda_c),
            "silenced_only": [c["id"] for c in cuda_c if c["verdict"] == "silenced_only"],
        },
    }
    (DATA / "silent.json").write_text(json.dumps(out, indent=1) + "\n")
    a = out["arvo"]
    print(
        f"ARVO ({' + '.join(f'{r} {n}' for r, n in a['silenced_by_run'].items())}): "
        f"{a['silenced']} candidates silenced the sanitizer.\n"
        f"  rejected by later gate checks: {a['rejected_total']} {a['rejected_by_gate']}\n"
        f"  verified: {a['verified']} -> review: correct {a['correct']}, defensive {defensive}, "
        f"wrong {wrong} {a['review_of_verified']}\n"
        f"  not fixes = {a['rejected_total']} + {wrong} = {not_fixes} of {a['silenced']} "
        f"({a['not_fixes_pct']}%); the gate caught {a['rejected_total']} of {not_fixes} "
        f"({a['caught_by_gate_pct']}%)\n"
        f"  head-to-head: {json.dumps(a['head_to_head'])}\n"
        f"Juliet: {out['juliet']['silenced']} silenced, {out['juliet']['verified']} verified\n"
        f"CUDA: {out['cuda']['silenced']} silenced, {out['cuda']['verified']} verified, "
        f"silenced only: {out['cuda']['silenced_only']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
