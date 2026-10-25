#!/usr/bin/env python3
"""Semantic audit of every verified ARVO candidate against the developer's fix (D-0069).

scripts/semantic_audit.py            -> runs/semantic_audit/<case>.json (resumes; one Ultra call
                                        per distinct verified diff per case)
scripts/semantic_audit.py --dry-run  -> list what would be classified, no model calls

Advisory: the hand adjudication in cases/arvo/semantic_adjudication.json is what NUMBERS uses.
"""

from __future__ import annotations

import argparse
import json
import sys

from leakproof.config import RUNS_DIR, load_dotenv
from leakproof.edits import unified_diff
from leakproof.llm import CostLedger, LLMClient
from leakproof.semantic import (
    change,
    classify,
    developer,
    originals,
    verified_candidates,
    wide_diff,
)

OUT = RUNS_DIR / "semantic_audit"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--budget", type=float, default=1.8)
    args = ap.parse_args()
    load_dotenv()
    cases = verified_candidates()
    OUT.mkdir(parents=True, exist_ok=True)
    client = (
        None
        if args.dry_run
        else LLMClient(ledger=CostLedger(budget=args.budget), run_id="semantic_audit")
    )
    for case, c in sorted(cases.items()):
        dev = developer(case)
        if dev is None:
            print(f"{case}: no developer fix, skipped")
            continue
        out = OUT / f"{case}.json"
        done = json.loads(out.read_text()) if out.exists() else {"case": case, "candidates": []}
        seen = {x["change"]: x for x in done["candidates"]}
        dev_wide = wide_diff(dev["files"], dev["diff"])
        for key, cand in c["candidates"].items():
            # The rebuilt originals must reproduce the stored diff, or the context is wrong.
            back = unified_diff(originals(cand["files"], cand["diff"]), cand["files"])
            assert change(back) == key, f"{case}: reverse-apply mismatch"
            if key in seen and "class" in seen[key]:
                seen[key]["members"] = cand["members"]
                continue
            print(
                f"{case}: {len(cand['members'])} member(s), {len(cand['diff'])} chars", flush=True
            )
            if args.dry_run:
                continue
            res = classify(
                client,
                c["finding"],
                c["root_cause"],
                dev_wide,
                wide_diff(cand["files"], cand["diff"]),
            )
            seen[key] = {"change": key, "diff": cand["diff"], "members": cand["members"], **res}
            print(f"  -> {res['class']}: {res['reason'][:160]}", flush=True)
            done["candidates"] = list(seen.values())
            done["developer_diff"] = dev["diff"]
            out.write_text(json.dumps(done, indent=1))
        if seen:
            done["candidates"] = list(seen.values())
            done["developer_diff"] = dev["diff"]
            if not args.dry_run:
                out.write_text(json.dumps(done, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
