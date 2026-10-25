#!/usr/bin/env python3
"""Re-select winners in existing ARVO runs under D-0070 (no new worker calls).

For every run record with 2+ distinct verified diffs: the pairwise Ultra knockout
(leakproof.winner), plus the cross-candidate differential verdict when runs/cross_diff has
one. Writes runs/winners.json: {run: {case: {old, new, ambiguous, log}}}; resumes from it.
"""

from __future__ import annotations

import argparse
import json
import sys

from leakproof.config import RUNS_DIR, load_dotenv
from leakproof.llm import CostLedger, LLMClient
from leakproof.semantic import RUNS, change
from leakproof.winner import choose, ultra_judge

OUT = RUNS_DIR / "winners.json"


def who(workers: list[dict], diff: str) -> dict:
    w = next(w for w in workers if w["diff"] == diff)
    return {
        "hypothesis_id": w["hypothesis_id"],
        "worker_index": w["worker_index"],
        "round": w.get("round", 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=1.2)
    args = ap.parse_args()
    load_dotenv()
    client = LLMClient(ledger=CostLedger(budget=args.budget), run_id="reselect")
    out = json.loads(OUT.read_text()) if OUT.exists() else {}
    for run in RUNS:
        for p in sorted((RUNS_DIR / run).glob("*.json")):
            if p.name == "summary.json":
                continue
            rec = json.loads(p.read_text())
            verified = [w for w in rec.get("workers", []) if w.get("verdict") == "verified"]
            distinct = list(dict.fromkeys(w["diff"] for w in verified))
            if len({change(d) for d in distinct}) < 2:
                continue
            row = out.setdefault(run, {}).get(rec["case"])
            if row is None:
                judge = ultra_judge(client, rec["finding"], rec["plan"].get("root_cause", ""))
                diff, log = choose(distinct, judge)
                row = {
                    "old": who(verified, rec["winner"]["diff"]),
                    "new": who(verified, diff),
                    "log": log,
                }
                out[run][rec["case"]] = row
                OUT.write_text(json.dumps(out, indent=1))
                print(run, rec["case"], row["old"], "->", row["new"], flush=True)
            cross = RUNS_DIR / "cross_diff" / f"{rec['case']}.json"
            if cross.exists():
                cd = json.loads(cross.read_text())
                if "groups" in cd:
                    # Groups index the case's distinct verified diffs across runs; only this
                    # run's members count.
                    keys = [c["change"] for c in cd["candidates"]]
                    mine = {keys.index(change(d)) for d in distinct if change(d) in keys}
                    hit = [g for g in cd["groups"] if mine & set(g)]
                    row["ambiguous"] = len(hit) > 1
            OUT.write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
